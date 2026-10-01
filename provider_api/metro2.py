"""Metro 2 field helpers.

The database stores the real single-character ECOA domain and the real
24-character payment history profile. Those are correct but unreadable, so
everything that renders or reasons about them goes through here rather than
hardcoding a character.
"""

from __future__ import annotations

# Real Metro 2 ECOA codes. Only the three we model are listed; the rest of the
# domain (5 co-maker, 7 maker, T terminated, W business, X deceased, Z delete)
# is out of scope for this POC.
ECOA_INDIVIDUAL = "1"
ECOA_JOINT = "2"
ECOA_AUTHORIZED_USER = "3"

ECOA_LABELS = {
    ECOA_INDIVIDUAL: "individual",
    ECOA_JOINT: "joint (contractually liable)",
    ECOA_AUTHORIZED_USER: "authorized user",
}

# Payment history profile codes, most-recent-month-first in the stored string.
PAYMENT_CODE_LABELS = {
    "0": "current (0-29 days)",
    "1": "30-59 days past due",
    "2": "60-89 days past due",
    "3": "90-119 days past due",
    "4": "120-149 days past due",
    "5": "150-179 days past due",
    "6": "180+ days past due",
    "B": "no history (account did not exist)",
}


def ecoa_label(code: str | None) -> str:
    return ECOA_LABELS.get((code or "").strip(), f"unknown ECOA code {code!r}")


def is_authorized_user(code: str | None) -> bool:
    return (code or "").strip() == ECOA_AUTHORIZED_USER


# The profile's encoding, stated once in the tool description rather than
# repeated inside every tradeline. A credit file with seven accounts repeated it
# seven times, and every later turn in the conversation resent all seven.
PAYMENT_HISTORY_LEGEND = (
    "Payment history profiles read most recent month first: '0' current, "
    "'1'-'6' increasing delinquency (30-59 days through 180+), 'B' no history "
    "because the account did not exist yet."
)


def summarize_payment_history(profile: str | None) -> dict:
    """Turn the 24-character profile into something a model can reason over
    without having to count characters.

    Deliberately does not carry the legend: see PAYMENT_HISTORY_LEGEND, which
    the tool description states once into the cached prefix."""
    if not profile:
        return {"months_reported": 0, "note": "No payment history profile reported."}
    reported = [c for c in profile if c != "B"]
    delinquent = [(i, c) for i, c in enumerate(profile) if c not in ("0", "B")]
    worst = max((c for _, c in delinquent), default="0")
    return {
        "profile": profile,
        "months_reported": len(reported),
        "months_delinquent": len(delinquent),
        "worst_status": PAYMENT_CODE_LABELS.get(worst, worst),
        # months_ago is the index: position 0 is the most recent month.
        "delinquencies": [
            {"months_ago": i, "status": PAYMENT_CODE_LABELS.get(c, c)}
            for i, c in delinquent
        ],
        "all_paid_as_agreed": not delinquent,
    }
