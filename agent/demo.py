"""Demo mode — the full investigation with no API key and no cost.

This is not a mock of the app; it is a mock of one thing only. The real loop
runs, the real tools query the real database, the real audit_log row is written
and the real guardrails apply. What is replaced is the model: ``DemoClient``
stands in for the API client and returns a scripted sequence of turns, then
synthesizes the memo from the tool results it actually received.

So demo mode exercises everything except the reasoning. It is honest about that:
memos it produces are labelled, in the UI and in audit_log, as canned.

Turn on with ``DEMO_MODE=1``, the sidebar toggle, or ``investigate.py --demo``.
"""

from __future__ import annotations

import json
import os
from typing import Any

from provider_api import metro2

TRUTHY = {"1", "true", "yes", "on"}

DEMO_BANNER = (
    "> **Demo mode** — this memo was assembled by a canned analyzer from real "
    "tool results. No model call was made, so neither the reasoning nor the "
    "prose is model-generated."
)

# What the canned analyzer says when the analyst is chatting rather than asking
# for an investigation. It is deliberately explicit that no model answered.
DEMO_CHAT_REPLY = (
    "**Demo mode — no model call was made, so this is a canned reply.**\n\n"
    "In demo mode I can run a full investigation on the selected case: the real "
    "tools, the real provider lookups and the real audit trail, with the memo "
    "assembled from the actual tool results. Use **Run investigation** for "
    "that.\n\n"
    "Free-form questions need a live model, which needs an API key. Set "
    "`ANTHROPIC_API_KEY` and switch demo mode off in the sidebar to ask them."
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
    ssn = results.get("check_ssn_verification", {}).get("result", {}) or {}
    credit = results.get("check_credit_trajectory", {}).get("result", {}) or {}
    au = results.get("check_authorized_user_history", {}).get("result", {}) or {}
    shared = results.get("check_shared_identifiers", {}).get("result", {}) or {}

    header_mismatch = ssn.get("dob_consistent_with_header") is False
    ecbsv_match = ssn.get("ecbsv_match") is True
    first_observed = ssn.get("ssn_first_observed")
    issuance_notes = ssn.get("notes") or ""
    # The seeded notes say so explicitly when an absent history is unremarkable.
    benign_history = "not by itself" in issuance_notes or "routine" in issuance_notes

    tradelines = credit.get("tradelines") or []
    au_lines = au.get("tradelines") or []
    util = credit.get("aggregate_utilization_pct")
    delinquent_accounts = credit.get("accounts_ever_delinquent") or 0

    matches = shared.get("matches") or []
    velocity = shared.get("velocity") or []
    linked_ids = shared.get("distinct_linked_applicants") or []
    # The tightest window in which one value was seen across several
    # applications. This is the signal that separates a ring from coincidence.
    tightest = velocity[0] if velocity else None
    ring_velocity = bool(
        tightest
        and tightest["span_days"] <= 30
        and len(tightest["applicants_touched"]) >= 3
    )

    first_party_led = (
        case["first_party_synthetic_score"] > case["third_party_synthetic_score"]
    )

    # --- timeline
    timeline = []
    if first_observed:
        timeline.append({
            "date": str(first_observed),
            "event": f"SSN first appears in credit-header data ({first_observed}).",
            "significance": (
                f"Nothing before this date, though the claimed DOB of "
                f"{case['claimed_dob']} implies decades of prior records."
                if header_mismatch
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
    own = [t for t in tradelines if t.get("ecoa_code") != metro2.ECOA_AUTHORIZED_USER]
    if own:
        timeline.append({
            "date": own[0]["account_open_date"],
            "event": f"First account in own name: {own[0]['creditor']}.",
            "significance": "Start of an independent file.",
        })
    for line in own[-2:]:
        if line is own[0] and len(own) > 1:
            continue
        history = line.get("payment_history") or {}
        timeline.append({
            "date": line["account_open_date"],
            "event": (
                f"{line['creditor']} opened — {_money(line['credit_limit'])} limit, "
                f"{_money(line['balance'])} balance, {line['status']}."
            ),
            "significance": (
                "Near-full utilization on a recently opened line, still paying as "
                "agreed — the shape credit is in just before a bust-out."
                if line.get("credit_limit") and line.get("balance")
                and line["balance"] > 0.85 * line["credit_limit"]
                and history.get("all_paid_as_agreed")
                else "Part of the recent growth in exposure."
            ),
        })
    if tightest and ring_velocity:
        timeline.append({
            "date": tightest["first_seen"],
            "event": (
                f"Same {tightest['identifier_type']} ({tightest['identifier_value']}) "
                f"seen across applicants {tightest['applicants_touched']} within "
                f"{tightest['span_days']} days."
            ),
            "significance": "Shared infrastructure inside a single short window.",
        })
    timeline.sort(key=lambda step: step["date"])

    # --- evidence
    evidence = []
    if ssn:
        evidence.append({
            "finding": (
                "SSA returns a match on SSN, name and DOB"
                if ecbsv_match
                else "SSA does not match this SSN, name and DOB"
            ),
            "source_tool": "check_ssn_verification",
            "detail": (
                "eCBSV confirms the combination is on record. Note this is a point "
                "in the applicant's favour, and also what a well-aged synthetic "
                "identity looks like — a match alone separates nothing."
                if ecbsv_match
                else "No SSA match returned."
            ),
            "strength": "moderate",
        })
        evidence.append({
            "finding": (
                f"SSN has no credit-header presence before {first_observed}"
                if header_mismatch
                else f"Credit-header presence back to {first_observed}, consistent with the claimed DOB"
            ),
            "source_tool": "check_ssn_verification",
            "detail": issuance_notes,
            "strength": ("moderate" if benign_history else "strong") if header_mismatch else "strong",
        })
    if tradelines:
        evidence.append({
            "finding": f"{len(tradelines)} tradelines spanning "
                       f"{credit.get('first_account_open_date')} to "
                       f"{credit.get('most_recent_open_date')}",
            "source_tool": "check_credit_trajectory",
            "detail": (
                f"Total limit {_money(credit.get('total_credit_limit'))}, total balance "
                f"{_money(credit.get('total_balance'))}, aggregate utilization {util}%. "
                f"{delinquent_accounts} account(s) ever delinquent across the "
                "24-month payment history."
            ),
            "strength": "strong" if (util or 0) > 80 else "moderate",
        })
        if (util or 0) > 80 and delinquent_accounts == 0:
            evidence.append({
                "finding": "High utilization with a spotless payment history",
                "source_tool": "check_credit_trajectory",
                "detail": (
                    "Every month reports as paid as agreed while balances sit near "
                    "the limit. Stockpiling before a default looks exactly like "
                    "this; so does someone using credit heavily and servicing it."
                ),
                "strength": "moderate",
            })
    if au_lines:
        evidence.append({
            "finding": f"{len(au_lines)} authorized-user tradeline(s) (ECOA code 3), earliest "
                       f"{au.get('earliest_authorized_user_date')}",
            "source_tool": "check_authorized_user_history",
            "detail": ", ".join(
                f"{l['creditor']} ({_money(l['credit_limit'])})" for l in au_lines
            ),
            "strength": "moderate",
        })
    if matches:
        evidence.append({
            "finding": (
                f"Shares {len(shared.get('matching_identifier_types') or [])} identifier "
                f"type(s) with {len(linked_ids)} other flagged applicant(s)"
            ),
            "source_tool": "check_shared_identifiers",
            "detail": "; ".join(
                f"{v['identifier_type']} {v['identifier_value']} across applicants "
                f"{v['applicants_touched']} over {v['span_days']} days"
                for v in velocity
            ) or "; ".join(
                f"{m['identifier_type']} {m['identifier_value']} → applicant "
                f"{m['linked_applicant_id']}" for m in matches
            ),
            "strength": "strong" if ring_velocity else "moderate",
        })
        if ring_velocity:
            evidence.append({
                "finding": (
                    f"Three applications from one {tightest['identifier_type']} inside "
                    f"{tightest['span_days']} days"
                ),
                "source_tool": "check_shared_identifiers",
                "detail": (
                    f"{tightest['identifier_value']} seen {tightest['first_seen']} to "
                    f"{tightest['last_seen']} across applicants "
                    f"{tightest['applicants_touched']}. Velocity this tight is the "
                    "hardest single signal here to explain innocently."
                ),
                "strength": "strong",
            })
    else:
        evidence.append({
            "finding": "No identifier appears on any other flagged application",
            "source_tool": "check_shared_identifiers",
            "detail": shared.get("note", "No matches returned."),
            "strength": "moderate",
        })

    # --- confidence
    if header_mismatch and ring_velocity:
        confidence = "high"
    elif header_mismatch and matches:
        confidence = "high"
    elif header_mismatch:
        confidence = "low" if benign_history else "medium"
    elif matches:
        confidence = "medium"
    else:
        confidence = "low"

    # --- counter-narrative
    paragraphs = []
    if ecbsv_match:
        paragraphs.append(
            "**On the SSA match.** eCBSV confirms this SSN, name and date of birth "
            "go together in SSA's records. That is a genuine point for the "
            "applicant and it is the check most decisioning treats as "
            "authoritative. It is worth being clear why it is not decisive here: "
            "a synthetic identity that has been reported to the bureaus for years "
            "will pass it too. The match rules out a crude fabrication, not a "
            "patient one."
        )
    if header_mismatch:
        paragraphs.append(
            "**On the missing credit history.** An SSN with no header presence "
            "before a recent date fits an identity that was built rather than "
            "lived. It equally fits someone who immigrated as an adult, someone "
            "who was never enumerated at birth, and someone who has simply never "
            "borrowed. Note also what this signal is not: SSA randomized number "
            "assignment in June 2011, so for a number issued after that nobody "
            "can infer an issuance date from the number itself — first-observed "
            "is a statement about our records, not about the person. "
            + (
                f"The record says as much here: \"{issuance_notes}\" That is an "
                "argument for the applicant, not against them."
                if benign_history
                else "What would settle it: immigration or work-authorization "
                "records, or any pre-dating non-credit record — a lease, a "
                "utility account, a tax filing."
            )
        )
    else:
        paragraphs.append(
            "**On identity.** Header presence runs back far enough to match the "
            "claimed date of birth, and SSA agrees with the combination. Whatever "
            "else is true of this application, the core identity behaves like a "
            "real one, and a synthetic-identity disposition would be hard to "
            "support."
        )
    if au_lines:
        paragraphs.append(
            "**On the authorized-user line.** Piggybacking is how synthetic "
            "identities are matured, and it is also how a parent puts a teenager "
            "on a card or how a spouse shares an account. Metro 2 records ECOA "
            "code 3 either way — the field captures the mechanism, not the "
            "relationship. What would settle it: the host account holder's "
            "identity and their relationship to this applicant."
        )
    if matches and ring_velocity:
        paragraphs.append(
            f"**On the shared {tightest['identifier_type']}.** The honest reading "
            "is that this is the weakest part of the applicant's case. A shared "
            "address can be a real multi-tenant building and a shared IP can be a "
            f"household or a carrier NAT range, but {tightest['span_days']} days "
            f"across {len(tightest['applicants_touched'])} applications is a "
            "different claim from the same value appearing at some point. What "
            "would still help them: whether the address is a genuine residential "
            "unit, and whether the device match holds at full fingerprint depth "
            "rather than a single id that a shared machine would also produce."
        )
    elif matches:
        paragraphs.append(
            "**On the shared identifiers.** The matches are spread over "
            f"{max(v['span_days'] for v in velocity) if velocity else 'many'} days, "
            "which is much more consistent with a shared building, a recycled "
            "phone number or a carrier address range than with one operator "
            "running several applications. Matching is exact-value only, so these "
            "say two applications touched the same value — not that one person "
            "controls both."
        )
    else:
        paragraphs.append(
            "**On the absence of links.** Nothing on this application appears on "
            "any other flagged file — no shared phone, address, device, email or "
            "IP. Fabricated identities are rarely built alone, because keeping "
            "the infrastructure behind them separate costs money. This is the "
            "strongest single point in the applicant's favour."
        )
    if delinquent_accounts:
        paragraphs.append(
            f"**On the payment history.** {delinquent_accounts} account(s) show a "
            "delinquency in the 24-month profile. That cuts toward the applicant "
            "rather than against them: manufactured files are managed, and a "
            "late payment that was then cured is the kind of ordinary mess real "
            "people make and rings avoid."
        )
    if first_party_led and not header_mismatch:
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

    # --- summary
    if first_party_led and not header_mismatch:
        summary = (
            f"{case['name']} scores {case['abuse_score']} but the evidence points "
            "away from a fabricated identity: SSA matches, header history runs "
            "back decades, and nothing links this file to another flagged "
            "application. The recent limit stacking is a real concern — it just "
            "points at first-party abuse by a real person."
        )
    elif confidence == "high":
        detail = (
            f"the same {tightest['identifier_type']} across applicants "
            f"{tightest['applicants_touched']} inside {tightest['span_days']} days"
            if ring_velocity
            else f"identifiers shared with {len(linked_ids)} other flagged applicant(s)"
        )
        summary = (
            f"{case['name']}'s file shows the full synthetic pattern: an SSN that "
            f"passes SSA but has no credit history before {first_observed} against "
            f"a claimed DOB of {case['claimed_dob']}, an authorized-user line "
            f"supplying instant file age, and {detail}. The combination is much "
            "harder to explain innocently than any one signal alone."
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
    def __init__(self, case: dict, investigate: bool = True) -> None:
        self.case = case
        self.investigate = investigate
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

        if not self.investigate:
            # An ordinary chat turn. Ending with text and no tool call is what
            # tells the loop this is a complete reply.
            return self._emit([_text(DEMO_CHAT_REPLY)], "end_turn")

        if self.turn == 1:
            return self._emit(
                [
                    _thinking(
                        f"Reason codes are {self.case['reason_codes']}. Start with "
                        "SSN verification, since an SSA match with no credit "
                        "history behind it reframes everything else, and pull the "
                        "trajectory alongside it for the payment profiles."
                    ),
                    _tool_use("demo_1", "check_ssn_verification", {"applicant_id": applicant_id}),
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
                        "application — with the velocity, not just the fact of a "
                        "match."
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
    """Quacks like the API client for the one call the loop makes."""

    def __init__(self, case: dict, investigate: bool = True) -> None:
        self.beta = _Block(messages=_DemoMessages(case, investigate=investigate))
