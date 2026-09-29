"""Offline smoke test for the tool-use loop.

Runs the whole loop against a stubbed Claude client, so it needs no API key and
costs nothing. It checks the parts that are easy to get wrong: tool results are
fed back with the right tool_use_id, the scope guard rejects a foreign
applicant_id, submit_case_memo terminates the loop and writes exactly one
audit_log row, and that row's analyst_decision is left NULL.

    python -m tests.test_loop
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import loop, record_analyst_decision  # noqa: E402
from db import seed  # noqa: E402


class Block:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class Response:
    def __init__(self, content, stop_reason):
        self.content = content
        self.stop_reason = stop_reason
        self.stop_details = None


class StubMessages:
    """Replays a scripted sequence of responses and records what it was sent."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def create(self, **kwargs):
        # The loop mutates one messages list in place, so snapshot it.
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        return self.script.pop(0)


class StubClient:
    def __init__(self, script):
        self.beta = Block(messages=StubMessages(script))


MEMO = {
    "timeline": [
        {"date": "2022-04-11", "event": "Added as authorized user on a $15,000 line.",
         "significance": "Instant file age with no repayment history."},
    ],
    "evidence": [
        {"finding": "SSN issued long after the claimed DOB", "source_tool": "check_ssn_issuance",
         "detail": "Issuance window 2016-2018 vs claimed DOB 1991-03-14.", "strength": "strong"},
    ],
    "counter_narrative": "An adult-issued SSN also fits someone who immigrated as an adult.",
    "confidence_level": "high",
    "summary": "Pattern is consistent with a matured synthetic identity.",
}


def build_script():
    return [
        # Turn 1: two lookups at once, one of them out of scope.
        Response(
            [
                Block(type="thinking", thinking="Start with the issuance mismatch."),
                Block(type="tool_use", id="tu_1", name="check_ssn_issuance",
                      input={"applicant_id": 1}),
                Block(type="tool_use", id="tu_2", name="check_credit_trajectory",
                      input={"applicant_id": 2}),  # foreign id — must be refused
            ],
            "tool_use",
        ),
        # Turn 2: a server-side web search that pauses.
        Response(
            [
                Block(type="server_tool_use", name="web_search",
                      input={"query": "mail drop address synthetic identity"}),
                Block(type="web_search_tool_result", content=[{"title": "x"}]),
            ],
            "pause_turn",
        ),
        # Turn 3: resumed, then submits.
        Response(
            [
                Block(type="text", text="Enough to write this up."),
                Block(type="tool_use", id="tu_3", name="submit_case_memo", input=MEMO),
            ],
            "tool_use",
        ),
    ]


def main() -> int:
    tmp = Path(tempfile.mkdtemp()) / "cases.db"
    seed.build(tmp, seed.SCHEMA_PATH)

    client = StubClient(build_script())
    events = list(loop.run_investigation(1, client=client, db_path=tmp))
    kinds = [e["type"] for e in events]
    failures = []

    def check(condition, message):
        if not condition:
            failures.append(message)

    check(kinds[0] == "start", f"first event should be start, got {kinds[0]}")
    check(kinds[-1] == "done", f"last event should be done, got {kinds[-1]}")
    check("search" in kinds, "the web_search block should surface as a search event")

    results = [e for e in events if e["type"] == "tool_result"]
    scoped = [e for e in results if e["tool"] == "check_ssn_issuance"]
    refused = [e for e in results if e["tool"] == "check_credit_trajectory"]
    check(scoped and not scoped[0]["is_error"], "in-scope lookup should succeed")
    check(refused and refused[0]["is_error"], "out-of-scope applicant_id should be refused")
    check("out of scope" in refused[0]["output"], "refusal should say why")

    # The loop must feed results back keyed to the originating tool_use_id.
    second_call = client.beta.messages.calls[1]
    sent_back = second_call["messages"][-1]["content"]
    check({r["tool_use_id"] for r in sent_back} == {"tu_1", "tu_2"},
          "both tool results must be returned in one user message")

    # pause_turn must be resumed rather than ending the run.
    check(len(client.beta.messages.calls) == 3,
          f"expected 3 API calls (one resuming the paused turn), got "
          f"{len(client.beta.messages.calls)}")

    memo_events = [e for e in events if e["type"] == "memo"]
    check(len(memo_events) == 1, "exactly one memo event")

    conn = sqlite3.connect(tmp)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM audit_log").fetchall()
    check(len(rows) == 1, f"exactly one audit_log row, got {len(rows)}")
    row = rows[0]
    check(row["analyst_decision"] is None, "analyst_decision must stay NULL after the agent runs")
    check(row["confidence_level"] == "high", "confidence level should be persisted")
    check("Counter-narrative" in row["case_memo"], "memo must carry a counter-narrative section")
    trail = json.loads(row["tool_calls_made"])
    check([t["tool"] for t in trail] ==
          ["check_ssn_issuance", "check_credit_trajectory", "web_search", "submit_case_memo"],
          f"trail should record every call in order, got {[t['tool'] for t in trail]}")

    # Only the analyst path can set a decision.
    record_analyst_decision(row["id"], "escalated", "Want the AU host's file.", db_path=tmp)
    after = conn.execute("SELECT * FROM audit_log WHERE id = ?", (row["id"],)).fetchone()
    check(after["analyst_decision"] == "escalated", "analyst decision should persist")
    check(after["decided_at"] is not None, "decided_at should be stamped")
    conn.close()

    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        return 1
    print(f"ok — {len(events)} events, {len(trail)} tool calls, audit_log clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
