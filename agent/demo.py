"""Demo mode — the full investigation with no API key and no cost.

This is not a mock of the app; it is a mock of one thing only. The real loop
runs, the real tools query the real database, the real audit_log row is written
and the real guardrails apply. What is replaced is Claude: ``DemoClient`` stands
in for the client and returns a scripted sequence of turns, then synthesizes the
memo from the tool results it actually received.

So demo mode exercises everything except the reasoning. It is honest about that:
memos it produces are labelled, in the UI and in audit_log, as canned.

Turn on with ``DEMO_MODE=1``, the sidebar toggle, or ``investigate.py --demo``.
"""

from __future__ import annotations

import json
import os
from typing import Any

TRUTHY = {"1", "true", "yes", "on"}

DEMO_BANNER = (
    "> **Demo mode** — this memo was assembled by a canned analyzer from real "
    "tool results. No model call was made, so the reasoning and the prose are "
    "not Claude's."
)


def is_demo_mode() -> bool:
    return os.environ.get("DEMO_MODE", "").strip().lower() in TRUTHY


# --- block shapes the loop expects -----------------------------------------


class _Block:
    def __init__(self, **kw: Any) -> None:
        self.__dict__.update(kw)

    def __repr__(self) -> str:  # helps when a test prints one
        return f"_Block({self.__dict__})"


class _Response:
    def __init__(self, content: list[_Block], stop_reason: str) -> None:
        self.content = content
        self.stop_reason = stop_reason
        self.stop_details = None


def _thinking(text: str) -> _Block:
    return _Block(type="thinking", thinking=text)


def _text(text: str) -> _Block:
    return _Block(type="text", text=text)


def _tool_use(call_id: str, name: str, tool_input: dict) -> _Block:
    return _Block(type="tool_use", id=call_id, name=name, input=tool_input)


# --- memo synthesis ---------------------------------------------------------


def _money(value: Any) -> str:
    return f"${value:,}" if isinstance(value, (int, float)) else str(value)


def _synthesize_memo(case: dict, results: dict[str, dict]) -> dict:
    """Build a memo from what the tools actually returned for this case."""
    ssn = results.get("check_ssn_issuance", {}).get("result", {}) or {}
    credit = results.get("check_credit_trajectory", {}).get("result", {}) or {}
    au = results.get("check_authorized_user_history", {}).get("result", {}) or {}
    shared = results.get("check_shared_identifiers", {}).get("result", {}) or {}

    mismatch = ssn.get("dob_matches_issuance") is False
    issuance_notes = ssn.get("notes") or ""
    # The seeded notes say so explicitly when adult issuance is unremarkable.
    benign_issuance = "not by itself" in issuance_notes or "routine" in issuance_notes
    tradelines = credit.get("tradelines") or []
    au_lines = au.get("tradelines") or []
    matches = shared.get("matches") or []
    linked_ids = shared.get("distinct_linked_applicants") or []
    util = credit.get("aggregate_utilization_pct")
    first_party_led = (
        case["first_party_synthetic_score"] > case["third_party_synthetic_score"]
    )

    # --- timeline
    timeline = []
    if ssn.get("issuance_period"):
        timeline.append({
            "date": str(ssn["issuance_period"]).split("-")[0],
            "event": f"SSN issued (window {ssn['issuance_period']}).",
            "significance": (
                f"Issued long after the claimed DOB of {case['claimed_dob']}."
                if mismatch
                else f"Consistent with the claimed DOB of {case['claimed_dob']}."
            ),
        })
    for line in au_lines:
        timeline.append({
            "date": line["account_open_date"],
            "event": (
                f"Added as authorized user on {line['creditor']} "
                f"({_money(line['credit_limit'])} limit)."
            ),
            "significance": (
                "Inherits the host account's age and limit without any repayment "
                "history of its own."
            ),
        })
    own = [t for t in tradelines if t["ecoa_code"] != "authorized_user"]
    if own:
        timeline.append({
            "date": own[0]["account_open_date"],
            "event": f"First account in own name: {own[0]['creditor']}.",
            "significance": "Start of an independent file.",
        })
    for line in own[-2:]:
        if line is own[0] and len(own) > 1:
            continue
        timeline.append({
            "date": line["account_open_date"],
            "event": (
                f"{line['creditor']} opened — {_money(line['credit_limit'])} limit, "
                f"{_money(line['balance'])} balance, {line['status']}."
            ),
            "significance": (
                "Near-full utilization on a recently opened line."
                if line["credit_limit"] and line["balance"]
                and line["balance"] > 0.85 * line["credit_limit"]
                else "Part of the recent growth in exposure."
            ),
        })
    timeline.sort(key=lambda step: step["date"])

    # --- evidence
    evidence = []
    if ssn:
        evidence.append({
            "finding": (
                "Claimed DOB is inconsistent with SSN issuance"
                if mismatch
                else "SSN issuance is consistent with the claimed DOB"
            ),
            "source_tool": "check_ssn_issuance",
            "detail": f"Issuance window {ssn.get('issuance_period')}. {issuance_notes}",
            "strength": ("moderate" if benign_issuance else "strong") if mismatch else "strong",
        })
    if tradelines:
        evidence.append({
            "finding": f"{len(tradelines)} tradelines spanning "
                       f"{credit.get('first_account_open_date')} to "
                       f"{credit.get('most_recent_open_date')}",
            "source_tool": "check_credit_trajectory",
            "detail": (
                f"Total limit {_money(credit.get('total_credit_limit'))}, total balance "
                f"{_money(credit.get('total_balance'))}, aggregate utilization {util}%."
            ),
            "strength": "strong" if (util or 0) > 80 else "moderate",
        })
    if au_lines:
        evidence.append({
            "finding": f"{len(au_lines)} authorized-user tradeline(s), earliest "
                       f"{au.get('earliest_authorized_user_date')}",
            "source_tool": "check_authorized_user_history",
            "detail": ", ".join(
                f"{l['creditor']} ({_money(l['credit_limit'])})" for l in au_lines
            ),
            "strength": "moderate",
        })
    evidence.append({
        "finding": (
            f"Shares {len(shared.get('matching_identifier_types') or [])} identifier "
            f"type(s) with {len(linked_ids)} other flagged applicant(s)"
            if matches
            else "No identifier appears on any other flagged application"
        ),
        "source_tool": "check_shared_identifiers",
        "detail": (
            "; ".join(
                f"{m['identifier_type']} {m['identifier_value']} → applicant "
                f"{m['linked_applicant_id']} ({m['linked_applicant_name']}, "
                f"score {m['linked_abuse_score']})"
                for m in matches
            )
            if matches
            else shared.get("note", "No matches returned.")
        ),
        "strength": "strong" if len(linked_ids) > 1 else ("moderate" if matches else "moderate"),
    })

    # --- confidence
    if mismatch and matches:
        confidence = "high"
    elif mismatch:
        confidence = "low" if benign_issuance else "medium"
    elif matches:
        confidence = "medium"
    else:
        confidence = "low"

    # --- counter-narrative
    paragraphs = []
    if mismatch:
        paragraphs.append(
            "**On the issuance mismatch.** An SSN issued after the claimed birth "
            "date is the signature of a fabricated identity, but it is not unique "
            "to one. It is also what you see for someone who immigrated as an "
            "adult, someone never enumerated at birth, or a replacement number "
            "issued after identity theft. "
            + (
                f"The issuance record itself says as much here: \"{issuance_notes}\" "
                "That is an argument for the applicant, not against them."
                if benign_issuance
                else "What would settle it: immigration or work-authorization records, "
                "or SSA detail on why the number was enumerated when it was."
            )
        )
    else:
        paragraphs.append(
            "**On identity.** The issuance check is clean — the SSN was issued in a "
            "window consistent with the claimed date of birth. Whatever else is "
            "true of this application, the core identity behaves like a real one, "
            "and a synthetic-identity disposition would be hard to support."
        )
    if au_lines:
        paragraphs.append(
            "**On the authorized-user line.** Piggybacking is how synthetic "
            "identities are matured, and it is also how a parent puts a teenager "
            "on a card, or how a spouse shares an account. The mechanism is "
            "identical; only the relationship differs. What would settle it: the "
            "host account holder's identity and their relationship to this "
            "applicant."
        )
    if matches:
        paragraphs.append(
            "**On the shared identifiers.** A shared address can be a genuine "
            "multi-tenant building or a sublet; a shared IP can be a household, a "
            "carrier-grade NAT range, or a café. Matching is exact-value only, so "
            "these say two applications touched the same value — not that one "
            "person controls both. What would settle it: whether the address is a "
            "real residential unit, and whether the device match holds up at full "
            "fingerprint depth rather than a single id."
        )
    else:
        paragraphs.append(
            "**On the absence of links.** Nothing on this application appears on "
            "any other flagged file — no shared phone, address, device, email or "
            "IP. Fabricated identities are rarely built alone, because the "
            "infrastructure behind them costs money to keep separate. This is the "
            "strongest single point in the applicant's favour."
        )
    if first_party_led and not mismatch:
        paragraphs.append(
            "**On what this more likely is.** The provider's first-party "
            f"sub-score ({case['first_party_synthetic_score']}) sits well above "
            f"its third-party sub-score ({case['third_party_synthetic_score']}), "
            "and the file shows a long clean history before the recent run-up. "
            "That shape fits a real person misusing their own credit — distress "
            "or intent to default — rather than an invented one. Those need "
            "different handling, and treating this as a synthetic identity would "
            "mean working the wrong case."
        )
    if (util or 0) > 80:
        paragraphs.append(
            f"**On the {util}% utilization.** Near-full balances across recently "
            "opened lines fit pre-default stockpiling. They also fit someone in "
            "genuine financial trouble, which is common and is not fraud. What "
            "would settle it: payment behaviour over the next two cycles."
        )

    # --- summary
    if first_party_led and not mismatch:
        summary = (
            f"{case['name']} scores {case['abuse_score']} but the evidence points "
            "away from a fabricated identity: issuance is clean and nothing links "
            "this file to another flagged application. The recent limit stacking "
            "and utilization are real concerns — they just point at first-party "
            "abuse by a real person."
        )
    elif confidence == "high":
        summary = (
            f"{case['name']}'s file shows the full synthetic pattern: an SSN issued "
            f"{ssn.get('issuance_period')} against a claimed DOB of "
            f"{case['claimed_dob']}, an authorized-user line providing instant "
            f"file age, and identifiers shared with {len(linked_ids)} other flagged "
            "applicant(s). The three together are much harder to explain innocently "
            "than any one alone."
        )
    elif confidence == "low":
        summary = (
            f"{case['name']} scores {case['abuse_score']}, but each signal has a "
            "plausible innocent reading and no identifier links this file to "
            "another flagged application. Read this as a likely false positive "
            "unless further evidence changes the picture."
        )
    else:
        summary = (
            f"{case['name']} shows some of the synthetic pattern but not all of it. "
            "The evidence supports a closer look rather than a conclusion."
        )

    return {
        "timeline": timeline,
        "evidence": evidence,
        "counter_narrative": "\n\n".join(paragraphs),
        "confidence_level": confidence,
        "summary": summary,
    }


# --- the stand-in client ----------------------------------------------------


class _DemoMessages:
    def __init__(self, case: dict) -> None:
        self.case = case
        self.turn = 0
        self._pending: dict[str, str] = {}   # tool_use_id -> tool name
        self.results: dict[str, dict] = {}

    def _absorb(self, messages: list[dict]) -> None:
        """Read the tool results the loop fed back, the way a model would."""
        if not messages:
            return
        last = messages[-1]
        if last.get("role") != "user" or not isinstance(last.get("content"), list):
            return
        for item in last["content"]:
            if not isinstance(item, dict) or item.get("type") != "tool_result":
                continue
            name = self._pending.get(item.get("tool_use_id", ""))
            if not name:
                continue
            try:
                self.results[name] = json.loads(item["content"])
            except (json.JSONDecodeError, TypeError, KeyError):
                self.results[name] = {}

    def _emit(self, blocks: list[_Block], stop_reason: str) -> _Response:
        for block in blocks:
            if block.type == "tool_use":
                self._pending[block.id] = block.name
        return _Response(blocks, stop_reason)

    def create(self, **kwargs: Any) -> _Response:
        self._absorb(kwargs.get("messages") or [])
        self.turn += 1
        applicant_id = self.case["id"]

        if self.turn == 1:
            return self._emit(
                [
                    _thinking(
                        f"Reason codes are {self.case['reason_codes']}. Start with "
                        "issuance, since a mismatch reframes everything else, and "
                        "pull the trajectory alongside it."
                    ),
                    _tool_use("demo_1", "check_ssn_issuance", {"applicant_id": applicant_id}),
                    _tool_use("demo_2", "check_credit_trajectory", {"applicant_id": applicant_id}),
                ],
                "tool_use",
            )

        if self.turn == 2:
            return self._emit(
                [
                    _thinking(
                        "Now the two questions that separate a manufactured file "
                        "from a thin but real one: where the file age came from, "
                        "and whether anything here appears on another flagged "
                        "application."
                    ),
                    _tool_use("demo_3", "check_authorized_user_history", {"applicant_id": applicant_id}),
                    _tool_use("demo_4", "check_shared_identifiers", {"applicant_id": applicant_id}),
                ],
                "tool_use",
            )

        memo = _synthesize_memo(self.case, self.results)
        return self._emit(
            [
                _text(
                    "Four lookups is enough to write this up, with the "
                    "counter-narrative argued signal by signal."
                ),
                _tool_use("demo_5", "submit_case_memo", memo),
            ],
            "tool_use",
        )


class DemoClient:
    """Quacks like ``anthropic.Anthropic`` for the one call the loop makes."""

    def __init__(self, case: dict) -> None:
        self.beta = _Block(messages=_DemoMessages(case))
