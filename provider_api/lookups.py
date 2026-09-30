"""The lookup logic itself, independent of transport.

Both callers use these: the FastAPI handlers in main.py, and the agent's
``direct`` transport when it bypasses HTTP. Sharing them is what makes the
transports interchangeable — if the HTTP path and the in-process path built
their own SQL, their response shapes would drift and the agent would see
different evidence depending on how it was wired.

Each function takes an open connection and returns the provider-shaped
``{"request": ..., "result": ...}`` envelope.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any

from . import metro2


class LookupNotFound(Exception):
    """No such applicant."""


def _applicant(conn: sqlite3.Connection, applicant_id: int) -> dict:
    row = conn.execute("SELECT * FROM applicants WHERE id = ?", (applicant_id,)).fetchone()
    if row is None:
        raise LookupNotFound(f"No such applicant: {applicant_id}")
    return dict(row)


def _provider_request(applicant: dict, fields: list[str]) -> dict:
    """The outbound payload as a real provider would take it: attributes, not
    our internal row id."""
    return {k: applicant[k] for k in fields}


def ssn_verification(conn: sqlite3.Connection, applicant_id: int) -> dict[str, Any]:
    applicant = _applicant(conn, applicant_id)
    row = conn.execute(
        """SELECT ecbsv_match, ssn_first_observed, dob_consistent_with_header, notes
             FROM ssn_verification_checks WHERE applicant_id = ?""",
        (applicant_id,),
    ).fetchone()
    request = _provider_request(applicant, ["name", "ssn", "claimed_dob"])
    if row is None:
        return {"request": request, "result": "no_record",
                "note": "No verification record on file for this applicant."}
    return {
        "request": request,
        "result": {
            # What eCBSV actually returns: a match, and nothing about issuance.
            "ecbsv_match": bool(row["ecbsv_match"]),
            # The separate identity-graph signal.
            "ssn_first_observed": row["ssn_first_observed"],
            "dob_consistent_with_header": bool(row["dob_consistent_with_header"]),
            "notes": row["notes"],
        },
    }


def credit_trajectory(conn: sqlite3.Connection, applicant_id: int) -> dict[str, Any]:
    applicant = _applicant(conn, applicant_id)
    rows = conn.execute(
        """SELECT account_open_date, ecoa_code, creditor, credit_limit, balance,
                  status, payment_history_profile
             FROM tradelines WHERE applicant_id = ? ORDER BY account_open_date""",
        (applicant_id,),
    ).fetchall()
    tradelines = []
    for r in rows:
        item = dict(r)
        item["ecoa"] = metro2.ecoa_label(item["ecoa_code"])
        item["payment_history"] = metro2.summarize_payment_history(
            item.pop("payment_history_profile")
        )
        tradelines.append(item)
    total_limit = sum(t["credit_limit"] or 0 for t in tradelines)
    total_balance = sum(t["balance"] or 0 for t in tradelines)
    ever_delinquent = [
        t for t in tradelines if not t["payment_history"].get("all_paid_as_agreed", True)
    ]
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
            "accounts_ever_delinquent": len(ever_delinquent),
            "tradelines": tradelines,
        },
    }


def authorized_user_history(conn: sqlite3.Connection, applicant_id: int) -> dict[str, Any]:
    applicant = _applicant(conn, applicant_id)
    rows = conn.execute(
        """SELECT account_open_date, creditor, credit_limit, balance, status,
                  payment_history_profile
             FROM tradelines
            WHERE applicant_id = ? AND ecoa_code = ?
            ORDER BY account_open_date""",
        (applicant_id, metro2.ECOA_AUTHORIZED_USER),
    ).fetchall()
    au = []
    for r in rows:
        item = dict(r)
        item["ecoa"] = metro2.ecoa_label(metro2.ECOA_AUTHORIZED_USER)
        item["payment_history"] = metro2.summarize_payment_history(
            item.pop("payment_history_profile")
        )
        au.append(item)
    return {
        "request": _provider_request(applicant, ["name", "ssn", "claimed_dob"]),
        "result": {
            "authorized_user_tradeline_count": len(au),
            "earliest_authorized_user_date": au[0]["account_open_date"] if au else None,
            "tradelines": au,
            "note": (
                "ECOA code 3 identifies an authorized user in Metro 2. The code "
                "cannot distinguish a fraud ring's piggyback from a parent "
                "adding a child."
            ),
        },
    }


def shared_identifiers(conn: sqlite3.Connection, applicant_id: int) -> dict[str, Any]:
    applicant = _applicant(conn, applicant_id)
    rows = conn.execute(
        """SELECT si.identifier_type, si.identifier_value, si.linked_applicant_id,
                  si.first_seen, si.last_seen,
                  a.name AS linked_applicant_name,
                  s.abuse_score AS linked_abuse_score,
                  s.risk_tier AS linked_risk_tier
             FROM shared_identifiers si
             LEFT JOIN applicants a ON a.id = si.linked_applicant_id
             LEFT JOIN scores s ON s.applicant_id = si.linked_applicant_id
            WHERE si.applicant_id = ?
            ORDER BY si.first_seen, si.identifier_type""",
        (applicant_id,),
    ).fetchall()
    matches = [dict(r) for r in rows]
    linked_ids = sorted({m["linked_applicant_id"] for m in matches if m["linked_applicant_id"]})

    # Velocity: the window in which one identifier value was seen across
    # applications. This is what separates a ring from a coincidence.
    velocity = []
    by_value: dict[str, list[dict]] = {}
    for m in matches:
        by_value.setdefault(m["identifier_value"], []).append(m)
    for value, group in by_value.items():
        seen = sorted(d for m in group for d in (m["first_seen"], m["last_seen"]) if d)
        if len(seen) >= 2:
            velocity.append({
                "identifier_type": group[0]["identifier_type"],
                "identifier_value": value,
                "applicants_touched": sorted(
                    {applicant_id, *(g["linked_applicant_id"] for g in group)}
                ),
                "first_seen": seen[0],
                "last_seen": seen[-1],
                "span_days": (
                    date.fromisoformat(seen[-1]) - date.fromisoformat(seen[0])
                ).days,
            })
    velocity.sort(key=lambda v: v["span_days"])

    return {
        "request": _provider_request(
            applicant, ["name", "claimed_address", "claimed_phone", "claimed_email"]
        ),
        "result": {
            "match_count": len(matches),
            "distinct_linked_applicants": linked_ids,
            "matching_identifier_types": sorted({m["identifier_type"] for m in matches}),
            "matches": matches,
            "velocity": velocity,
            "note": (
                "Exact-value match only; near-matches are out of scope. "
                "Velocity spans matter in both directions — a tight window is "
                "hard to explain innocently, a wide one is evidence for a "
                "shared building or carrier rather than one operator."
                if matches
                else "No identifier on this application appears on any other "
                     "flagged application."
            ),
        },
    }


LOOKUPS = {
    "check_ssn_verification": ssn_verification,
    "check_credit_trajectory": credit_trajectory,
    "check_authorized_user_history": authorized_user_history,
    "check_shared_identifiers": shared_identifiers,
}


# The agent-facing descriptions, defined once. Both the MCP server and the
# agent's direct transport read these, so the two can never drift into
# describing the same lookup differently.
LOOKUP_DESCRIPTIONS = {
    "check_ssn_verification": (
        "Check an applicant's SSN against two separate signals: the eCBSV match "
        "(does SSA agree this SSN, name and DOB go together) and the earliest "
        "date the SSN appears in credit-header data. A fabricated identity "
        "often passes the match while having no history before it was built, so "
        "the match alone proves very little — read the two together."
    ),
    "check_credit_trajectory": (
        "Return the applicant's credit accounts in date order with Metro 2 "
        "fields: open date, ECOA code, creditor, limit, balance, status, and "
        "the 24-month payment history profile. Use the payment history to tell "
        "a bust-out from ordinary borrowing — balances alone cannot show it."
    ),
    "check_authorized_user_history": (
        "Return only the tradelines where this identity is an authorized user "
        "on someone else's account (Metro 2 ECOA code 3). This is the credit "
        "piggybacking that matures synthetic identities, and also the ordinary "
        "way a parent helps a teenager build credit."
    ),
    "check_shared_identifiers": (
        "Return phone, address, device, email or IP values on this application "
        "that also appear on other flagged applications, with first/last "
        "sighting dates and a velocity span for each value. Exact match only. "
        "A tight span across several applicants is a strong ring signal; a wide "
        "one is evidence for a shared building or carrier instead."
    ),
}
