"""Run one investigation from the terminal — same agent loop the UI drives.

Useful for watching the agent work without Streamlit in the way.

    python investigate.py 1
    python investigate.py --list
"""

from __future__ import annotations

import argparse
import json
import textwrap

import agent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("applicant_id", nargs="?", type=int)
    parser.add_argument("--list", action="store_true", help="list flagged cases and exit")
    parser.add_argument("--json", action="store_true", help="dump raw events as JSON lines")
    args = parser.parse_args(argv)

    if args.list or args.applicant_id is None:
        for case in agent.list_cases():
            decided = case["latest_decision"] or "—"
            print(f"{case['id']:>3}  {case['abuse_score']:>3}  {case['risk_tier']:<6} "
                  f"{case['name']:<22} {case['reason_codes']}  [{decided}]")
        return 0

    for event in agent.run_investigation(args.applicant_id):
        if args.json:
            print(json.dumps(event, default=str))
            continue
        kind = event["type"]
        if kind == "start":
            case = event["case"]
            print(f"\n=== {case['name']} (applicant {case['id']}) — "
                  f"{case['abuse_score']}, {case['risk_tier']} risk ===\n")
        elif kind == "thinking":
            print(textwrap.indent(textwrap.fill(event["text"], 88), "  · "))
        elif kind == "narration":
            print(textwrap.fill(event["text"], 90))
        elif kind == "tool_call":
            print(f"\n→ {event['tool']}({event['input']})")
        elif kind == "search":
            print(f"\n→ web_search({event['query']!r})")
        elif kind == "tool_result":
            flag = "ERROR " if event.get("is_error") else ""
            print(f"  ← {flag}{event['output'][:300]}")
        elif kind == "memo":
            print("\n" + "=" * 90)
            print(event["markdown"])
            print("=" * 90)
            print(f"\nWritten to audit_log row {event['audit_log_id']} "
                  f"(analyst_decision is NULL — a human decides).")
        elif kind == "error":
            print(f"\n!! {event['message']}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
