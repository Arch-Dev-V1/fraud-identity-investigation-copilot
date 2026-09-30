"""Offline smoke test for the tool-use loop, demo mode and the MCP transport.

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

from agent import demo, loop, record_analyst_decision  # noqa: E402
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
        {"date": "2022-04-11", "event": "Added as authorized user (ECOA 3) on a $15,000 line.",
         "significance": "Instant file age with no repayment history."},
    ],
    "evidence": [
        {"finding": "SSN has no credit-header presence before 2016-08", "source_tool": "check_ssn_verification",
         "detail": "First observed 2016-08 vs claimed DOB 1991-03-14.", "strength": "strong"},
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
                Block(type="tool_use", id="tu_1", name="check_ssn_verification",
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


def check_demo_mode(failures: list[str]) -> None:
    """Demo mode must run the whole investigation with no client and no network,
    label the memo as canned, and still write exactly one audit_log row."""
    tmp = Path(tempfile.mkdtemp()) / "cases.db"
    seed.build(tmp, seed.SCHEMA_PATH)

    for applicant_id, expected in [(1, "high"), (4, "low"), (6, "low")]:
        events = list(loop.run_investigation(applicant_id, db_path=tmp, demo_mode=True))
        memos = [e for e in events if e["type"] == "memo"]
        if len(memos) != 1:
            failures.append(f"demo applicant {applicant_id}: expected one memo")
            continue
        memo = memos[0]
        got = memo["memo"]["confidence_level"]
        if got != expected:
            failures.append(
                f"demo applicant {applicant_id}: expected {expected} confidence, got {got}"
            )
        if demo.DEMO_BANNER not in memo["markdown"]:
            failures.append(f"demo applicant {applicant_id}: memo is not labelled as canned")
        if not memo["memo"]["counter_narrative"].strip():
            failures.append(f"demo applicant {applicant_id}: empty counter-narrative")
        if events[-1]["type"] != "done":
            failures.append(f"demo applicant {applicant_id}: run did not complete")

    conn = sqlite3.connect(tmp)
    rows = conn.execute(
        "SELECT applicant_id, analyst_decision FROM audit_log ORDER BY applicant_id"
    ).fetchall()
    conn.close()
    if [r[0] for r in rows] != [1, 4, 6]:
        failures.append(f"demo mode should write one row per case, got {rows}")
    if any(r[1] is not None for r in rows):
        failures.append("demo mode must still leave analyst_decision NULL")


def check_chat_turn(failures: list[str]) -> None:
    """A chat turn must answer without writing a memo, and conversation history
    must carry from one turn to the next."""
    tmp = Path(tempfile.mkdtemp()) / "cases.db"
    seed.build(tmp, seed.SCHEMA_PATH)

    events = list(loop.run_investigation(
        1, db_path=tmp, demo_mode=True,
        user_message="What does ECOA code 3 mean?", require_memo=False,
    ))
    kinds = [e["type"] for e in events]
    if "reply" not in kinds:
        failures.append(f"a chat turn should yield a reply, got {kinds}")
    if "memo" in kinds:
        failures.append("a chat turn must not submit a memo")
    if kinds[-1] != "done":
        failures.append(f"a chat turn should finish cleanly, got {kinds[-1]}")

    conn = sqlite3.connect(tmp)
    rows = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    conn.close()
    if rows:
        failures.append(f"a chat turn must not write to audit_log, got {rows} row(s)")

    history = next(
        (e["messages"] for e in events if e["type"] == "turn_complete"), None
    )
    if not history:
        failures.append("a chat turn should report its messages for the next turn")
        return

    # A second turn on top of that history must keep the earlier messages.
    followup = list(loop.run_investigation(
        1, db_path=tmp, demo_mode=True, user_message="And the payment profile?",
        history=history, require_memo=False,
    ))
    grown = next((e["messages"] for e in followup if e["type"] == "turn_complete"), [])
    if len(grown) <= len(history):
        failures.append(
            f"history should grow across turns: {len(history)} -> {len(grown)}"
        )

    # An investigation turn on the same case still writes exactly one memo.
    list(loop.run_investigation(1, db_path=tmp, demo_mode=True))
    conn = sqlite3.connect(tmp)
    rows = conn.execute(
        "SELECT analyst_decision FROM audit_log"
    ).fetchall()
    conn.close()
    if len(rows) != 1:
        failures.append(f"one investigation should write one memo, got {len(rows)}")
    elif rows[0][0] is not None:
        failures.append("analyst_decision must still be NULL")


def check_mcp_transport(failures: list[str]) -> None:
    """Exercise the real MCP path — agent -> MCP server -> provider gateway ->
    SQLite — without a subprocess or a socket.

    The MCP server calls the gateway over HTTP, so httpx is swapped for a shim
    backed by FastAPI's TestClient. Everything else is the production path: the
    same MCPServer, the same bridge, the same tool conversion.
    """
    from fastapi.testclient import TestClient

    from agent import tools
    from agent.mcp_bridge import McpBridge
    from provider_api import main as provider_main
    import mcp_server.server as mcp_srv

    tmp = Path(tempfile.mkdtemp()) / "cases.db"
    seed.build(tmp, seed.SCHEMA_PATH)

    original_db, original_httpx = provider_main.DB_PATH, mcp_srv.httpx
    provider_main.DB_PATH = tmp
    client = TestClient(provider_main.app)

    class _Shim:
        HTTPError = Exception

        @staticmethod
        def get(url, timeout=None):
            # strip the configured base so TestClient sees a bare path
            return client.get(url.replace(mcp_srv.PROVIDER_API_URL, "") or "/")

    mcp_srv.httpx = _Shim
    try:
        with McpBridge(mcp_srv.server) as bridge:
            names = [t.name for t in bridge.list_tools()]
            if sorted(names) != sorted(tools.LOOKUP_NAMES):
                failures.append(f"MCP should publish the four lookups, got {names}")

            definitions = tools.build_tool_list(tools.TRANSPORT_MCP, bridge)
            if [d.get("name") for d in definitions][-2:] != ["web_search", "submit_case_memo"]:
                failures.append("web_search and submit_case_memo must stay agent-side")
            for d in definitions:
                if d.get("name") in tools.LOOKUP_NAMES:
                    schema = d["input_schema"]
                    if schema.get("additionalProperties") is not False:
                        failures.append(f"{d['name']}: converted schema must be strict")

            payload, is_error = tools.execute_tool(
                "check_shared_identifiers", {"applicant_id": 1}, 1,
                transport=tools.TRANSPORT_MCP, bridge=bridge,
            )
            if is_error:
                failures.append(f"MCP lookup failed: {payload[:160]}")
            else:
                result = json.loads(payload)["result"]
                spans = [v["span_days"] for v in result["velocity"]]
                if not spans or min(spans) != 11:
                    failures.append(f"velocity should come through MCP, got {spans}")

            # The scope guard must hold on the MCP path too.
            _, guarded = tools.execute_tool(
                "check_credit_trajectory", {"applicant_id": 2}, 1,
                transport=tools.TRANSPORT_MCP, bridge=bridge,
            )
            if not guarded:
                failures.append("scope guard must reject a foreign id over MCP as well")

            # Both transports must agree, or the agent sees different evidence
            # depending on how it was wired.
            via_mcp, _ = tools.execute_tool(
                "check_ssn_verification", {"applicant_id": 6}, 6,
                transport=tools.TRANSPORT_MCP, bridge=bridge,
            )
            via_direct, _ = tools.execute_tool(
                "check_ssn_verification", {"applicant_id": 6}, 6,
                db_path=tmp, transport=tools.TRANSPORT_DIRECT,
            )
            if json.loads(via_mcp) != json.loads(via_direct):
                failures.append("the mcp and direct transports returned different payloads")
    finally:
        mcp_srv.httpx = original_httpx
        provider_main.DB_PATH = original_db
        client.close()


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
    scoped = [e for e in results if e["tool"] == "check_ssn_verification"]
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
          ["check_ssn_verification", "check_credit_trajectory", "web_search", "submit_case_memo"],
          f"trail should record every call in order, got {[t['tool'] for t in trail]}")

    # Only the analyst path can set a decision.
    record_analyst_decision(row["id"], "escalated", "Want the AU host's file.", db_path=tmp)
    after = conn.execute("SELECT * FROM audit_log WHERE id = ?", (row["id"],)).fetchone()
    check(after["analyst_decision"] == "escalated", "analyst decision should persist")
    check(after["decided_at"] is not None, "decided_at should be stamped")
    conn.close()

    check_demo_mode(failures)
    check_chat_turn(failures)
    check_mcp_transport(failures)

    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        return 1
    print(f"ok — {len(events)} events, {len(trail)} tool calls, audit_log clean; "
          "demo mode ok on 3 cases; chat turns ok; mcp transport ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
