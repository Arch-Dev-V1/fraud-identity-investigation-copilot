"""Tool definitions and implementations.

Every SQLite tool takes only ``applicant_id``. An ID is unambiguous where names
and DOBs collide, the model cannot mistype it into a different person, and it
keeps personal data out of ``audit_log.tool_calls_made``. Inside each tool the
code reads the name, DOB, SSN and so on from ``applicants`` and builds a
provider-shaped request itself — which is what a real provider call looks like
(they take attributes, not our internal row id) while the agent only ever
handles one safe value.

A tool will only accept the applicant_id of the case under investigation; any
other id comes back as a tool error, not a lookup.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from . import db

# --- schemas the model sees -------------------------------------------------

_APPLICANT_ID_SCHEMA = {
    "type": "object",
    "properties": {
        "applicant_id": {
            "type": "integer",
            "description": "The id of the applicant under investigation.",
        }
    },
    "required": ["applicant_id"],
    "additionalProperties": False,
}


def _lookup_tool(name: str, description: str) -> dict:
    return {
        "name": name,
        "description": description,
        "strict": True,
        "input_schema": _APPLICANT_ID_SCHEMA,
    }


SUBMIT_CASE_MEMO = {
    "name": "submit_case_memo",
    "description": (
        "Submit the finished case memo and end the investigation. This is "
        "advisory only: it records your analysis for a human analyst and does "
        "not approve, reject, escalate or otherwise dispose of the case. Call "
        "it exactly once, after the evidence is strong enough to stand on its "
        "own and the counter-narrative is genuinely substantive."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "timeline": {
                "type": "array",
                "description": (
                    "The identity's maturation history in date order — how this "
                    "identity was built up over time."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "date": {
                            "type": "string",
                            "description": "YYYY-MM-DD, or YYYY-MM / YYYY if that is all the evidence supports.",
                        },
                        "event": {
                            "type": "string",
                            "description": "What happened, in one sentence.",
                        },
                        "significance": {
                            "type": "string",
                            "description": "Why this step matters to the assessment.",
                        },
                    },
                    "required": ["date", "event", "significance"],
                    "additionalProperties": False,
                },
            },
            "evidence": {
                "type": "array",
                "description": "Each finding, tied to the tool that produced it.",
                "items": {
                    "type": "object",
                    "properties": {
                        "finding": {"type": "string"},
                        "source_tool": {
                            "type": "string",
                            "description": "The tool this finding came from.",
                        },
                        "detail": {
                            "type": "string",
                            "description": "The specific values that support it — dates, amounts, identifiers.",
                        },
                        "strength": {
                            "type": "string",
                            "enum": ["weak", "moderate", "strong"],
                        },
                    },
                    "required": ["finding", "source_tool", "detail", "strength"],
                    "additionalProperties": False,
                },
            },
            "counter_narrative": {
                "type": "string",
                "description": (
                    "The substantive case that this applicant is a real person "
                    "and the flag is wrong: the innocent explanation for each "
                    "major signal, and what evidence would settle it. Not a "
                    "disclaimer — argue it properly."
                ),
            },
            "confidence_level": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": (
                    "Confidence that this is a synthetic identity. Never a "
                    "yes/no verdict."
                ),
            },
            "summary": {
                "type": "string",
                "description": "Two or three sentences an analyst can read first.",
            },
        },
        "required": [
            "timeline",
            "evidence",
            "counter_narrative",
            "confidence_level",
            "summary",
        ],
        "additionalProperties": False,
    },
}

# web_search is Anthropic-hosted: declared here so the tool list is in one
# place, but there is no implementation below because it does not run locally.
WEB_SEARCH = {
    "type": "web_search_20260209",
    "name": "web_search",
    "max_uses": 4,
}

TOOLS: list[dict] = [
    _lookup_tool(
        "check_ssn_issuance",
        "Check whether the applicant's claimed date of birth is consistent with "
        "how and when their SSN was actually issued. A mismatch is the single "
        "strongest synthetic-identity signal, but it has innocent causes.",
    ),
    _lookup_tool(
        "check_credit_trajectory",
        "Return the applicant's credit account history in date order: open "
        "dates, creditors, limits, balances and status. Use it to see how the "
        "file was built — organic growth looks different from a manufactured "
        "ramp.",
    ),
    _lookup_tool(
        "check_authorized_user_history",
        "Return only the tradelines where the identity was added as an "
        "authorized user on someone else's account. This is the 'credit "
        "piggybacking' boost that synthetic identities are built with — and "
        "also the ordinary way a parent helps a teenager build credit.",
    ),
    _lookup_tool(
        "check_shared_identifiers",
        "Return phone, address, device, email or IP values on this application "
        "that also appear on other flagged applications. Exact match only. "
        "Rings invent names and SSNs cheaply but reuse infrastructure.",
    ),
    WEB_SEARCH,
    SUBMIT_CASE_MEMO,
]

# Tools that end the investigation when called.
TERMINAL_TOOLS = {"submit_case_memo"}
# Tools that run on Anthropic's servers — never dispatched locally.
SERVER_TOOLS = {"web_search"}


# --- implementations --------------------------------------------------------


def _provider_request(applicant: dict, fields: list[str]) -> dict:
    """Shape the outbound request the way a real provider would take it:
    attributes, not our internal row id."""
    return {k: applicant[k] for k in fields}


def check_ssn_issuance(conn, applicant: dict) -> dict:
    row = conn.execute(
        "SELECT dob_matches_issuance, issuance_period, notes"
        "  FROM ssn_issuance_checks WHERE applicant_id = ?",
        (applicant["id"],),
    ).fetchone()
    result: dict[str, Any] = {
        "request": _provider_request(applicant, ["name", "ssn", "claimed_dob"]),
    }
    if row is None:
        result["result"] = "no_record"
        result["note"] = "No issuance check on file for this applicant."
        return result
    result["result"] = {
        "dob_matches_issuance": bool(row["dob_matches_issuance"]),
        "issuance_period": row["issuance_period"],
        "notes": row["notes"],
    }
    return result


def check_credit_trajectory(conn, applicant: dict) -> dict:
    rows = conn.execute(
        """SELECT account_open_date, ecoa_code, creditor, credit_limit, balance, status
             FROM tradelines WHERE applicant_id = ?
            ORDER BY account_open_date""",
        (applicant["id"],),
    ).fetchall()
    tradelines = [dict(r) for r in rows]
    total_limit = sum(t["credit_limit"] or 0 for t in tradelines)
    total_balance = sum(t["balance"] or 0 for t in tradelines)
    return {
        "request": _provider_request(applicant, ["name", "ssn", "claimed_dob"]),
        "result": {
            "tradeline_count": len(tradelines),
            "first_account_open_date": tradelines[0]["account_open_date"] if tradelines else None,
            "most_recent_open_date": tradelines[-1]["account_open_date"] if tradelines else None,
            "total_credit_limit": total_limit,
            "total_balance": total_balance,
            "aggregate_utilization_pct": (
                round(100 * total_balance / total_limit, 1) if total_limit else None
            ),
            "tradelines": tradelines,
        },
    }


def check_authorized_user_history(conn, applicant: dict) -> dict:
    rows = conn.execute(
        """SELECT account_open_date, creditor, credit_limit, balance, status
             FROM tradelines
            WHERE applicant_id = ? AND ecoa_code = 'authorized_user'
            ORDER BY account_open_date""",
        (applicant["id"],),
    ).fetchall()
    au = [dict(r) for r in rows]
    return {
        "request": _provider_request(applicant, ["name", "ssn", "claimed_dob"]),
        "result": {
            "authorized_user_tradeline_count": len(au),
            "earliest_authorized_user_date": au[0]["account_open_date"] if au else None,
            "tradelines": au,
        },
    }


def check_shared_identifiers(conn, applicant: dict) -> dict:
    rows = conn.execute(
        """SELECT si.identifier_type, si.identifier_value, si.linked_applicant_id,
                  a.name AS linked_applicant_name, s.abuse_score AS linked_abuse_score,
                  s.risk_tier AS linked_risk_tier
             FROM shared_identifiers si
             LEFT JOIN applicants a ON a.id = si.linked_applicant_id
             LEFT JOIN scores s ON s.applicant_id = si.linked_applicant_id
            WHERE si.applicant_id = ?
            ORDER BY si.identifier_type, si.identifier_value""",
        (applicant["id"],),
    ).fetchall()
    matches = [dict(r) for r in rows]
    linked_ids = sorted({m["linked_applicant_id"] for m in matches if m["linked_applicant_id"]})
    return {
        "request": _provider_request(
            applicant, ["name", "claimed_address", "claimed_phone", "claimed_email"]
        ),
        "result": {
            "match_count": len(matches),
            "distinct_linked_applicants": linked_ids,
            "matching_identifier_types": sorted({m["identifier_type"] for m in matches}),
            "matches": matches,
            "note": (
                "Exact match only; near-matches are out of scope for this check."
                if matches
                else "No identifier on this application appears on any other flagged application."
            ),
        },
    }


_IMPLEMENTATIONS: dict[str, Callable] = {
    "check_ssn_issuance": check_ssn_issuance,
    "check_credit_trajectory": check_credit_trajectory,
    "check_authorized_user_history": check_authorized_user_history,
    "check_shared_identifiers": check_shared_identifiers,
}


class ToolError(Exception):
    """Returned to the model as an is_error tool_result, not raised to the UI."""


def execute_tool(
    name: str, tool_input: dict, case_applicant_id: int, db_path=None
) -> tuple[str, bool]:
    """Run one lookup. Returns ``(result_json, is_error)``."""
    impl = _IMPLEMENTATIONS.get(name)
    if impl is None:
        return json.dumps({"error": f"Unknown tool: {name}"}), True

    requested = tool_input.get("applicant_id")
    if requested != case_applicant_id:
        # The scope guard: a tool only ever answers for the case under
        # investigation, so the agent cannot wander into other people's files.
        return (
            json.dumps(
                {
                    "error": (
                        f"applicant_id {requested!r} is out of scope. This "
                        f"investigation covers applicant {case_applicant_id} only. "
                        "Other applicants surfaced by check_shared_identifiers are "
                        "context, not cases you can look up."
                    )
                }
            ),
            True,
        )

    conn = db.connect(db_path)
    try:
        applicant = conn.execute(
            "SELECT * FROM applicants WHERE id = ?", (case_applicant_id,)
        ).fetchone()
        if applicant is None:
            return json.dumps({"error": f"No such applicant: {case_applicant_id}"}), True
        return json.dumps(impl(conn, dict(applicant)), default=str), False
    except Exception as exc:  # surface as a tool error, keep the loop alive
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"}), True
    finally:
        conn.close()
