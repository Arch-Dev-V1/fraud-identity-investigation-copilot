"""Ground truth for the investigation eval.

The database generates applicants; this module owns the expected labels. They
are kept apart on purpose: a label that lived next to the data it describes
would be too easy to "fix" by editing the data.

Labels follow a stated policy rather than per-case intuition, so a
disagreement is a disagreement about the policy and can be argued:

    high   — the credit-header gap is inconsistent with the claimed DOB with no
             benign cause recorded, AND either a ring link at tight velocity
             (one identifier across 3+ applicants inside ~30 days) or an
             authorized-user boost followed by rapid stacking to near-full
             utilization.
    medium — signals are present but each has a plausible innocent reading, or
             they conflict: a gap with a cured delinquency, a shared identifier
             over a span long enough to be a building or a carrier range.
    low    — the header is consistent with the claimed DOB, OR the gap has an
             explicit benign cause recorded, OR there are no links and both the
             trajectory and the payment history are ordinary.

    A recorded benign cause carries a case to `low` on its own, EXCEPT where it
    comes with both an authorized-user boost and a shared identifier — the two
    together are the maturation pattern, and that returns the case to `medium`.
    This clause is what separates 15 (benign cause, a wide IP link, no AU →
    low) from 21 (benign cause, a wide phone link, AU boost → medium). Without
    it those two labels look arbitrary.

Note what `low` means here: low confidence that the IDENTITY IS FABRICATED. It
is not a judgement that the application is fine. Applicants 5 and 18 are real
people running first-party abuse — correctly `low` on synthetic identity, and
still a problem for the lender. The memo is expected to say so.
"""

from __future__ import annotations

# applicant_id -> (expected_confidence, tags, why this label)
EXPECTED: dict[int, tuple[str, tuple[str, ...], str]] = {
    # --- hand-built anchors (db/seed.py) ---
    1: ("high", ("ring", "anchor", "hand-built"),
        "Ring A anchor: header gap ~25y, AU boost, device+IP across 3 applicants in 11 days."),
    2: ("high", ("ring", "hand-built"),
        "Ring A: header gap ~27y, AU boost, shares address/device/IP with the ring."),
    3: ("high", ("ring", "hand-built"),
        "Ring A: header gap ~23y, AU boost, shares phone/device/IP; already past due."),
    4: ("low", ("legitimate", "thin-file", "hand-built"),
        "Real 22-year-old: header consistent, parent's AU line, low utilization, no links."),
    5: ("low", ("legitimate", "first-party-abuse", "hand-built"),
        "Real person, 20y clean history then a stacking spree. First-party abuse, not synthetic."),
    6: ("low", ("legitimate", "adult-issuance", "hand-built"),
        "Header gap with an explicit benign cause recorded (adult arrival). No links."),
    # --- synthesized (db/eval_cases.py) ---
    7: ("high", ("ring", "anchor", "synthesized"),
        "Ring B anchor: header gap ~27y, AU boost, email+IP across 3 applicants in 6 days."),
    8: ("high", ("ring", "synthesized"),
        "Ring B: header gap ~29y, AU boost, shares email/IP/address/device with the ring."),
    9: ("high", ("ring", "synthesized"),
        "Ring B: header gap ~25y, AU boost, shares email/IP/device with the ring."),
    10: ("high", ("lone-synthetic", "synthesized"),
         "Hardest high: header gap ~34y, AU boost, stacking to 75% utilization, and its "
         "only link is a device shared over 266 days — no tight ring velocity at all. "
         "Tests whether the agent can reach high without a ring to point at."),
    11: ("high", ("ring", "anchor", "synthesized"),
         "Ring C: header gap ~27y, AU boost, address+device across a pair in 9 days."),
    12: ("high", ("ring", "synthesized"),
         "Ring C: header gap ~26y, AU boost, address+device across a pair in 9 days."),
    13: ("low", ("legitimate", "thin-file", "synthesized"),
         "Header first observed a month after the parent's AU line — what a 16-year-old's "
         "first record looks like. No links."),
    14: ("low", ("legitimate", "synthesized"),
         "Header back to 1976, consistent. Organic trajectory, one cured 30-day late."),
    15: ("low", ("legitimate", "adult-issuance", "synthesized"),
         "Header gap with an explicit benign cause recorded (adult arrival). No links."),
    16: ("low", ("legitimate", "synthesized"),
         "Header consistent, organic trajectory, a joint line closed in 2023. No links."),
    17: ("low", ("legitimate", "thin-file", "synthesized"),
         "Header from enumeration at birth, two small accounts, low utilization. No links."),
    18: ("low", ("legitimate", "first-party-abuse", "synthesized"),
         "Second first-party case: header consistent back to 1993, recent stacking all current."),
    19: ("medium", ("ambiguous", "short-gap", "synthesized"),
         "Eight-year gap — too short to be a built identity, too long to ignore. No links."),
    20: ("medium", ("ambiguous", "wide-span-link", "synthesized"),
         "Header consistent, but shares the Ring A mail-drop address over 448 days. "
         "Same building is the innocent reading."),
    21: ("medium", ("ambiguous", "adult-issuance", "synthesized"),
         "Benign cause recorded for the gap, but an AU boost and a shared phone over "
         "589 days pull the other way."),
    22: ("medium", ("ambiguous", "conflicting", "synthesized"),
         "Header gap with no benign cause, no links, but a cured delinquency — "
         "manufactured files are managed, real people miss payments."),
    23: ("medium", ("ambiguous", "wide-span-link", "synthesized"),
         "Header consistent, ordinary trajectory, but shares a device with applicant 10 "
         "over 266 days."),
    24: ("medium", ("ambiguous", "short-gap", "synthesized"),
         "Twelve-year gap with no benign cause either way, plus an AU boost. No links."),
    25: ("medium", ("ambiguous", "wide-span-link", "synthesized"),
         "Header consistent, but shares an IP with two flagged applicants over wide "
         "spans — carrier NAT is the innocent reading."),
}

CONFIDENCE_ORDER = ("low", "medium", "high")


def expected_label(applicant_id: int) -> str:
    return EXPECTED[applicant_id][0]


def ordinal_score(expected: str, actual: str) -> float:
    """1.0 exact, 0.5 one tier off, 0.0 two tiers off.

    An ordinal score rather than exact match because the errors are not equal:
    calling a ring member `medium` is a worse miss than `high` but a far better
    one than `low`, and a binary pass rate throws that shape away — along with
    the resolution the eval needs to see small changes.
    """
    if actual not in CONFIDENCE_ORDER:
        return 0.0
    distance = abs(CONFIDENCE_ORDER.index(expected) - CONFIDENCE_ORDER.index(actual))
    return {0: 1.0, 1: 0.5, 2: 0.0}[distance]


def case_ids() -> list[int]:
    return sorted(EXPECTED)


def by_tag(tag: str) -> list[int]:
    return [i for i, (_, tags, _) in EXPECTED.items() if tag in tags]


def distribution() -> dict[str, int]:
    counts: dict[str, int] = {}
    for label, _, _ in EXPECTED.values():
        counts[label] = counts.get(label, 0) + 1
    return counts
