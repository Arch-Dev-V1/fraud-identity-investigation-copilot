"""The tool-use loop.

A manual loop rather than the SDK's beta tool runner, for three reasons: the
Streamlit UI needs an event per step to drive ``st.status``; ``web_search`` can
end a turn with ``pause_turn``, which the Python runner does not auto-resume;
and ``submit_case_memo`` has to terminate the loop rather than feed a result
back.

The loop is a generator. It yields events as they happen and never touches
Streamlit, so it can also be driven from a script or a test.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Iterator

import anthropic

from . import db, tools

MODEL = "claude-opus-5"
MAX_TOKENS = 16000
# Enough turns for every lookup, a couple of searches and a self-check.
MAX_TURNS = 20
# How many times we nudge a model that stops without submitting a memo.
MAX_NUDGES = 2

# Server-side refusal fallbacks: if a safety classifier declines the request,
# the API reroutes rather than handing back an empty turn. Drop the `betas` and
# `fallbacks` arguments below to turn this off.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

SYSTEM_PROMPT = """\
You are an investigator on a financial-crime team. A scoring provider has \
flagged an application as a possible synthetic identity — an identity that was \
fabricated rather than stolen, typically by pairing a real or unissued SSN with \
invented biographical details and then maturing it with credit until it can \
borrow at scale.

Your job is to reconstruct how this identity was built and hand a human analyst \
a memo they can act on. You are advisory. You do not approve, reject, escalate \
or close anything, and you have no tool that could — the analyst decides.

How to work:

- Start from what is actually suspicious about THIS case. The reason codes tell \
you where the provider's suspicion came from; they are a starting point, not a \
checklist to work through in order. A case flagged for first-party abuse needs a \
different investigation from one flagged for a shared device.
- After each tool result, decide whether you have enough or need more. Do not \
call tools you have no reason to call, and do not stop while an obvious \
question is unanswered.
- Use web_search only for general fraud-pattern context that genuinely changes \
your reading of the evidence — what a mail-drop address type looks like, how a \
known ring operates, whether a pattern is a recognised typology. Never search \
for the applicant. The identity is fabricated demo data; searching for it \
returns nothing and wastes a turn.
- The lookup tools only answer for the applicant under investigation. Other \
applicants surfaced by check_shared_identifiers are context you can reason \
about, not files you can open.

Two things the memo must get right:

1. The counter-narrative is not a disclaimer. Argue the case that this is a real \
person and the flag is wrong, as well as it can be argued, signal by signal. \
An SSN issued after the claimed birth date fits a fabricated identity — it also \
fits someone who immigrated as an adult, or was never enumerated at birth. An \
authorized-user tradeline is how synthetics are matured — it is also how a \
parent helps a teenager build credit. Say what evidence would settle each \
question. If the counter-narrative is genuinely weak, say why it is weak rather \
than leaving it thin.
2. Give a confidence level, never a verdict. "High confidence this identity was \
fabricated" is a finding. "This is fraud, reject it" is a decision that is not \
yours to make.

Before you submit, check your own work: is every claim in the evidence list tied \
to something a tool actually returned, and is the counter-narrative substantive? \
If not, go back and investigate further.

When you are done, call submit_case_memo exactly once.
"""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_opening_prompt(case: dict) -> str:
    """What the agent is told before it picks its first tool."""
    return f"""\
A new application has been flagged for review.

Applicant id: {case['id']}   (pass this id to the lookup tools)
Name:            {case['name']}
Claimed DOB:     {case['claimed_dob']}
SSN:             {case['ssn']}
Claimed address: {case['claimed_address']}
Claimed phone:   {case['claimed_phone']}
Claimed email:   {case['claimed_email']}

Provider score (0-999 scale, higher is riskier):
  Composite abuse score:  {case['abuse_score']}   (risk tier: {case['risk_tier']})
  First-party synthetic:  {case['first_party_synthetic_score']}
  Third-party synthetic:  {case['third_party_synthetic_score']}
  Reason codes:           {case['reason_codes']}

Investigate this case and submit a memo."""


def memo_to_markdown(memo: dict, case: dict) -> str:
    """Render the structured memo for the analyst and for audit_log."""
    lines = [
        f"## Case memo — {case['name']} (applicant {case['id']})",
        "",
        f"**Confidence this identity is synthetic: {memo['confidence_level'].upper()}**  ",
        "_Advisory only — no disposition has been made. The analyst decides._",
        "",
        memo["summary"],
        "",
        "### Maturation timeline",
        "",
    ]
    for step in memo.get("timeline", []):
        lines.append(f"- **{step['date']}** — {step['event']}  ")
        lines.append(f"  _{step['significance']}_")
    lines += ["", "### Evidence", ""]
    for item in memo.get("evidence", []):
        lines.append(
            f"- **{item['finding']}** ({item['strength']}) — {item['detail']}  "
        )
        lines.append(f"  _source: `{item['source_tool']}`_")
    lines += [
        "",
        "### Counter-narrative — the case that this is a real person",
        "",
        memo["counter_narrative"],
    ]
    return "\n".join(lines)


def _client() -> anthropic.Anthropic:
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        # An `ant auth login` profile also works, so this is a hint, not a hard stop.
        pass
    return anthropic.Anthropic()


def run_investigation(
    applicant_id: int,
    client: anthropic.Anthropic | None = None,
    db_path=None,
) -> Iterator[dict[str, Any]]:
    """Investigate one case, yielding events as they happen.

    Event types: ``start``, ``thinking``, ``narration``, ``tool_call``,
    ``tool_result``, ``search``, ``memo``, ``error``, ``done``.
    """
    client = client or _client()
    case = db.get_case(applicant_id, db_path)
    yield {"type": "start", "case": case}

    messages: list[dict[str, Any]] = [
        {"role": "user", "content": build_opening_prompt(case)}
    ]
    trail: list[dict[str, Any]] = []  # goes to audit_log.tool_calls_made
    nudges = 0

    for _ in range(MAX_TURNS):
        try:
            response = client.beta.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                thinking={"type": "adaptive", "display": "summarized"},
                tools=tools.TOOLS,
                messages=messages,
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
        except anthropic.APIStatusError as exc:
            yield {"type": "error", "message": f"API error {exc.status_code}: {exc}"}
            return
        except anthropic.APIConnectionError as exc:
            yield {"type": "error", "message": f"Could not reach the API: {exc}"}
            return

        if response.stop_reason == "refusal":
            detail = getattr(response, "stop_details", None)
            yield {
                "type": "error",
                "message": f"The model declined this request ({detail}).",
            }
            return

        # Surface everything in the turn before acting on it.
        for block in response.content:
            if block.type == "thinking" and getattr(block, "thinking", ""):
                yield {"type": "thinking", "text": block.thinking}
            elif block.type == "text" and block.text.strip():
                yield {"type": "narration", "text": block.text}
            elif block.type == "server_tool_use" and block.name == "web_search":
                query = (block.input or {}).get("query", "")
                trail.append({
                    "tool": "web_search",
                    "input": {"query": query},
                    "output": "(results returned by Anthropic's web search)",
                    "timestamp": _utcnow(),
                })
                yield {"type": "search", "query": query}
            elif block.type == "web_search_tool_result":
                content = block.content
                # An error comes back as an object, a success as a list.
                if isinstance(content, list):
                    yield {
                        "type": "tool_result",
                        "tool": "web_search",
                        "output": f"{len(content)} result(s)",
                        "is_error": False,
                    }
                else:
                    code = getattr(content, "error_code", "unknown_error")
                    yield {
                        "type": "tool_result",
                        "tool": "web_search",
                        "output": f"search failed: {code}",
                        "is_error": True,
                    }

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "pause_turn":
            # A long server-tool turn was paused; resend to let it continue.
            continue

        tool_uses = [b for b in response.content if b.type == "tool_use"]

        if not tool_uses:
            if nudges >= MAX_NUDGES:
                yield {
                    "type": "error",
                    "message": "The agent finished without submitting a case memo.",
                }
                return
            nudges += 1
            messages.append({
                "role": "user",
                "content": (
                    "You have not submitted a case memo yet. Either call another "
                    "lookup tool if evidence is still missing, or call "
                    "submit_case_memo now."
                ),
            })
            continue

        tool_results = []
        for tool_use in tool_uses:
            if tool_use.name in tools.TERMINAL_TOOLS:
                memo = dict(tool_use.input)
                trail.append({
                    "tool": tool_use.name,
                    "input": {"confidence_level": memo.get("confidence_level")},
                    "output": "memo written to audit_log",
                    "timestamp": _utcnow(),
                })
                markdown = memo_to_markdown(memo, case)
                audit_log_id = db.write_memo(
                    applicant_id=applicant_id,
                    tool_calls_made=json.dumps(trail, indent=2),
                    case_memo=markdown,
                    confidence_level=memo["confidence_level"],
                    db_path=db_path,
                )
                yield {
                    "type": "memo",
                    "memo": memo,
                    "markdown": markdown,
                    "audit_log_id": audit_log_id,
                    "trail": trail,
                }
                yield {"type": "done"}
                return

            yield {"type": "tool_call", "tool": tool_use.name, "input": tool_use.input}
            output, is_error = tools.execute_tool(
                tool_use.name, dict(tool_use.input), applicant_id, db_path
            )
            trail.append({
                "tool": tool_use.name,
                "input": dict(tool_use.input),
                "output": json.loads(output),
                "timestamp": _utcnow(),
            })
            yield {
                "type": "tool_result",
                "tool": tool_use.name,
                "output": output,
                "is_error": is_error,
            }
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": output,
                **({"is_error": True} if is_error else {}),
            })

        messages.append({"role": "user", "content": tool_results})

    yield {
        "type": "error",
        "message": f"Stopped after {MAX_TURNS} turns without a case memo.",
    }
