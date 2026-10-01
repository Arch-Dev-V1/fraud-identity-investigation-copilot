"""Run the investigation eval.

Calls the real entry point — agent.run_investigation — rather than
reconstructing the API call, so the eval exercises the actual loop, tools,
transport and retry behaviour.

    python -m evals.run --approve-harness          # first run records the harness sha
    python -m evals.run --reps 3
    python -m evals.run --no-judge                 # free: programmatic metrics only
    python -m evals.run --cases 1,4,19 --demo      # free wiring check, no API calls

Writes the contract the report builder reads:
    .claude/hillclimb/investigation/<variant>/results.jsonl
    .claude/hillclimb/investigation/<variant>/traces/<id>_rep<k>.json
    .claude/hillclimb/investigation/<variant>/errors.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from pathlib import Path
from typing import Any

import anthropic

import agent
from agent import db
from evals import cases, grade as grading

ROOT = Path(__file__).resolve().parent.parent
FLOW_DIR = ROOT / ".claude" / "hillclimb" / "investigation"
DEFAULT_TIMEOUT_S = 420.0
MAX_ATTEMPTS = 4
_write_lock = threading.Lock()


# --- harness integrity ------------------------------------------------------

def _harness_sha(state: dict) -> str:
    digest = hashlib.sha256()
    for rel in ["evals/run.py", "evals/grade.py", "evals/cases.py",
                *state.get("harness_paths", [])]:
        path = ROOT / rel
        digest.update(rel.encode())
        digest.update(path.read_bytes() if path.exists() else b"<missing>")
    return digest.hexdigest()[:16]


def _gate(state_path: Path, state: dict, approve: bool) -> None:
    """Refuse to run when the harness changed since it was approved.

    A silently edited runner or grader makes every earlier round
    incomparable. Re-approving is the user's call, never the runner's.

    Approving EXITS rather than falling through into a run: --approve-harness
    is a review step, and having it also start a live pass means a reviewer
    spends money by acknowledging a diff.
    """
    actual = _harness_sha(state)
    recorded = state.get("harness_sha")
    if approve:
        state["harness_sha"] = actual
        state_path.write_text(json.dumps(state, indent=2) + "\n")
        print(f"harness approved at sha {actual}. Re-run without "
              "--approve-harness to start the eval.")
        raise SystemExit(0)
    if recorded is None:
        print("The harness has not been approved yet. Review evals/run.py and "
              "evals/grade.py, then re-run with --approve-harness.", file=sys.stderr)
        raise SystemExit(2)
    if recorded != actual:
        print(f"Harness changed since approval (recorded {recorded}, now {actual}). "
              "Earlier rounds are not comparable to this one. Re-run with "
              "--approve-harness once you have reviewed the change.", file=sys.stderr)
        raise SystemExit(2)


# --- case execution ---------------------------------------------------------

def _case_summary(case: dict) -> str:
    return (f"Applicant {case['id']} ({case['name']}), claimed DOB {case['claimed_dob']}. "
            f"Provider abuse score {case['abuse_score']} ({case['risk_tier']} risk). "
            f"Reason codes: {case['reason_codes']}.")


def _run_once(applicant_id: int, demo: bool) -> dict[str, Any]:
    """One investigation. Returns everything the row and trace need."""
    started = time.monotonic()
    trace: list[dict[str, Any]] = [
        {"role": "system", "content": agent.loop.SYSTEM_PROMPT},
        {"role": "user", "content": agent.build_opening_prompt(db.get_case(applicant_id))},
    ]
    memo = None
    tools_called: set[str] = set()
    served_models: set[str] = set()
    usage_totals: dict[str, int] = {}
    web_searches = 0
    audit_log_id = None
    pending_thinking: str | None = None
    error = None

    for event in agent.run_investigation(applicant_id, demo_mode=demo, require_memo=True):
        kind = event["type"]
        if kind == "thinking":
            pending_thinking = event["text"]
        elif kind == "narration":
            trace.append({"role": "assistant", "content": event["text"],
                          **({"thinking": pending_thinking} if pending_thinking else {})})
            pending_thinking = None
        elif kind == "tool_call":
            tools_called.add(event["tool"])
            trace.append({"role": "tool_call", "name": event["tool"],
                          "content": json.dumps(event["input"], indent=2),
                          **({"thinking": pending_thinking} if pending_thinking else {})})
            pending_thinking = None
        elif kind == "search":
            web_searches += 1
            tools_called.add("web_search")
            trace.append({"role": "tool_call", "name": "web_search",
                          "content": json.dumps({"query": event["query"]}, indent=2)})
        elif kind == "tool_result":
            trace.append({"role": "tool_result", "content": event["output"]})
        elif kind == "usage":
            if event.get("model"):
                served_models.add(event["model"])
            usage_totals = event.get("totals") or {}
        elif kind == "memo":
            memo = event["memo"]
            audit_log_id = event["audit_log_id"]
            trace.append({"role": "assistant", "content": event["markdown"]})
        elif kind == "error":
            error = event["message"]

    return {
        "memo": memo, "trace": trace, "tools_called": tools_called,
        "served_models": served_models, "usage": usage_totals,
        "web_searches": web_searches, "audit_log_id": audit_log_id,
        "latency_s": round(time.monotonic() - started, 2), "error": error,
    }


def _with_retries(applicant_id: int, demo: bool, timeout_s: float) -> tuple[dict | None, int, str | None]:
    """Run one case with jittered backoff and a hard wall-clock ceiling.

    The ceiling reclaims the slot and stops further attempts; it cannot abort
    the underlying request, which may keep running and keep billing.
    """
    attempts = 0
    last = None
    for attempt in range(MAX_ATTEMPTS):
        attempts += 1
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(_run_once, applicant_id, demo).result(timeout=timeout_s), attempts, None
        except FutureTimeout:
            return None, attempts, "timeout"
        except (anthropic.RateLimitError, anthropic.InternalServerError) as exc:
            last = f"{type(exc).__name__}: {exc}"
            if attempt < MAX_ATTEMPTS - 1:
                time.sleep(min(2 ** attempt + random.uniform(0, 1), 30))
        except anthropic.APIStatusError as exc:
            return None, attempts, f"api_error_{exc.status_code}"
        except Exception as exc:
            return None, attempts, f"harness_error: {type(exc).__name__}: {exc}"
    return None, attempts, last or "exhausted_retries"


# --- the run ----------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", default="baseline")
    parser.add_argument("--model", default=None, help="override agent.loop.MODEL")
    parser.add_argument("--effort", default=None, help="low|medium|high|xhigh|max")
    parser.add_argument("--reps", type=int, default=3)
    parser.add_argument("--timeout-s", type=float, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--cases", default=None, help="comma-separated applicant ids")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--judge-model", default=grading.JUDGE_MODEL_DEFAULT)
    parser.add_argument("--no-judge", action="store_true")
    parser.add_argument("--demo", action="store_true",
                        help="canned analyzer, no API calls — wiring checks only")
    parser.add_argument("--approve-harness", action="store_true")
    args = parser.parse_args(argv)

    variant_dir = FLOW_DIR / args.variant
    (variant_dir / "traces").mkdir(parents=True, exist_ok=True)
    state_path = FLOW_DIR / "_state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    _gate(state_path, state, args.approve_harness)

    if args.model:
        agent.loop.MODEL = args.model
    if args.effort:
        agent.loop.EFFORT = args.effort

    ids = [int(x) for x in args.cases.split(",")] if args.cases else cases.case_ids()
    results_path = variant_dir / "results.jsonl"
    errors_path = variant_dir / "errors.jsonl"

    done = set()
    if results_path.exists():
        for line in results_path.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                done.add((row["prompt_id"], row.get("rep", 0)))

    work = [(i, r) for i in ids for r in range(args.reps) if (str(i), r) not in done]
    if not work:
        print(f"nothing to do — {len(done)} (case, rep) rows already in {results_path}")
        return 0
    print(f"{len(work)} (case, rep) runs · model {agent.loop.MODEL} · "
          f"{'demo (free)' if args.demo else 'LIVE — this spends money'} · "
          f"judge {'off' if (args.no_judge or args.demo) else args.judge_model}")

    judge_client = None if (args.no_judge or args.demo) else anthropic.Anthropic()
    started = time.monotonic()

    def one(job: tuple[int, int]) -> None:
        applicant_id, rep = job
        result, attempts, failure = _with_retries(applicant_id, args.demo, args.timeout_s)
        case = db.get_case(applicant_id)

        if result is None or result.get("error"):
            with _write_lock:
                with errors_path.open("a") as fh:
                    fh.write(json.dumps({
                        "prompt_id": str(applicant_id), "rep": rep,
                        "failure_class": failure or "no_memo",
                        "detail": (result or {}).get("error"),
                        "retry_count": attempts - 1,
                        "model": sorted((result or {}).get("served_models") or []),
                        "usage": (result or {}).get("usage") or {},
                    }) + "\n")
            print(f"  case {applicant_id} rep {rep}: FAILED ({failure or 'no memo'})")
            return

        # Served-model assertion: a substituted model invalidates the comparison.
        served = sorted(result["served_models"])
        if served and not args.demo:
            requested = agent.loop.MODEL
            if any(not m.startswith(requested.rsplit("-", 1)[0]) and m != requested for m in served):
                with _write_lock:
                    with errors_path.open("a") as fh:
                        fh.write(json.dumps({
                            "prompt_id": str(applicant_id), "rep": rep,
                            "failure_class": "served_model_mismatch",
                            "detail": f"requested {requested}, served {served}",
                            "retry_count": attempts - 1, "model": served,
                            "usage": result["usage"],
                        }) + "\n")
                print(f"  case {applicant_id} rep {rep}: served-model mismatch {served}")
                return

        judge = None
        judge_usage = None
        if judge_client is not None and result["memo"]:
            try:
                score, reasoning, judge_usage = grading.judge_counter_narrative(
                    result["memo"], _case_summary(case), judge_client, args.judge_model)
                judge = (score, reasoning)
            except Exception as exc:
                judge = (0.0, f"judge failed: {type(exc).__name__}: {exc}")

        audit_row = agent.get_memo(result["audit_log_id"]) if result["audit_log_id"] else None
        grades, notes = grading.grade(
            applicant_id, result["memo"], result["tools_called"], audit_row, judge)

        label, tags, _ = cases.EXPECTED[applicant_id]
        trace_name = f"{applicant_id}_rep{rep}.json"
        row = {
            "prompt_id": str(applicant_id), "rep": rep,
            "prompt": agent.build_opening_prompt(case),
            "tags": [f"expected:{label}", *tags],
            "status": "ok", "stop_reason": "end_turn",
            "grade": grades, "explanation": notes,
            "model": served[0] if served else ("demo" if args.demo else agent.loop.MODEL),
            "usage": result["usage"],
            "latency_s": result["latency_s"],
            "tool_calls": len([t for t in result["trace"] if t["role"] == "tool_call"]),
            "web_searches": result["web_searches"],
            "trace": f"{args.variant}/traces/{trace_name}",
            "meta": {"audit_log_id": result["audit_log_id"], "retry_count": attempts - 1,
                     "expected": label,
                     **({"judge_model": args.judge_model, "judge_usage": judge_usage}
                        if judge_usage else {})},
        }
        if judge_usage:
            row["judge_model"] = args.judge_model
            row["judge_usage"] = judge_usage

        with _write_lock:
            (variant_dir / "traces" / trace_name).write_text(
                json.dumps(result["trace"], indent=2))
            with results_path.open("a") as fh:      # one row per completed case
                fh.write(json.dumps(row) + "\n")
        print(f"  case {applicant_id} rep {rep}: conf={grades['confidence']} "
              f"guard={grades['guardrails']} cited={grades['evidence_cited']:.2f}"
              + (f" judge={grades['counter_narr']:.2f}" if "counter_narr" in grades else ""))

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        list(pool.map(one, work))

    elapsed = time.monotonic() - started
    rows = [json.loads(l) for l in results_path.read_text().splitlines() if l.strip()]
    print(f"\n{len(rows)} rows in {results_path} · {elapsed:.0f}s wall clock")
    _summarize(rows)
    return 0


def _summarize(rows: list[dict]) -> None:
    import math
    if not rows:
        return
    scores = [r["grade"]["confidence"] for r in rows if r.get("status") == "ok"]
    if not scores:
        return
    mean = sum(scores) / len(scores)
    half = 100 / math.sqrt(len(scores)) if scores else 0
    print(f"headline (confidence, ordinal): {mean:.3f}  ±{half:.0f} points "
          f"over {len(scores)} graded reps")
    # The product-critical cut: a legitimate applicant called high-confidence synthetic.
    fp = [r for r in rows if r["meta"].get("expected") == "low"
          and "expected:low" in r["tags"] and r["grade"]["confidence"] == 0.0]
    low_rows = [r for r in rows if r["meta"].get("expected") == "low"]
    if low_rows:
        print(f"false positives (legitimate graded high): {len(fp)}/{len(low_rows)}")


if __name__ == "__main__":
    raise SystemExit(main())
