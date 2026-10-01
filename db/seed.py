"""Generate the mock case database.

Everything in here is fabricated. The data is hand-built rather than randomly
generated because the point of the demo is that the agent reasons about a
specific case: a synthetic-identity ring, a first-party bust-out, and two cases
that score badly for innocent reasons. Random noise would give it nothing to
say in the counter-narrative.

    python db/seed.py            # create db/cases.db (refuses to clobber)
    python db/seed.py --force    # drop and rebuild
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import date
from pathlib import Path

# Importable both as `python db/seed.py` and as `db.seed`: the script form puts
# only db/ on the path, so the project root has to be added for the
# provider_api and db imports below to resolve.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from db import eval_cases                      # noqa: E402
from provider_api import metro2                 # noqa: E402

# Metro 2 ECOA codes — the real single-character domain, from the one module
# that owns the field so the seed and the lookups cannot disagree.
IND = metro2.ECOA_INDIVIDUAL
JOINT = metro2.ECOA_JOINT
AU = metro2.ECOA_AUTHORIZED_USER

# The 24-month payment history profiles are generated relative to this date,
# so the demo data stays internally consistent.
AS_OF = date(2025, 9, 1)

DB_DIR = Path(__file__).resolve().parent
DB_PATH = DB_DIR / "cases.db"
SCHEMA_PATH = DB_DIR / "schema.sql"


# --- applicants -------------------------------------------------------------
# (id, name, ssn, claimed_dob, claimed_address, claimed_phone, claimed_email)
#
# 1-3 are the "Riverbend" ring: fabricated identities built on SSNs issued in
# the mid-2010s, matured with authorized-user tradelines, sharing an address,
# a phone, a device and an IP between them.
# 4 is a real 22-year-old with a thin file — scores medium for entirely
# legitimate reasons.
# 5 is a real person running a first-party bust-out: 20 years of clean history,
# then a six-month limit-stacking spree.
# 6 is a real person who arrived in the US as an adult — her SSN issuance
# genuinely does not line up with her DOB, and that is not fraud.
APPLICANTS = [
    (1, "Marcus Delane Hoyt", "623-84-1190", "1991-03-14",
     "1420 Kelso Ave Unit 5, Tampa, FL 33605", "813-555-0146", "m.hoyt91@mailburst.net"),
    (2, "Tressa Lindqvist", "623-84-1204", "1988-07-02",
     "1420 Kelso Ave Unit 5, Tampa, FL 33605", "813-555-0192", "t.lindqvist@mailburst.net"),
    (3, "Devon Aguayo-Pratt", "623-84-1177", "1993-11-21",
     "88 Ridgeline Ct Apt 12, Brandon, FL 33511", "813-555-0146", "d.aguayo@mailburst.net"),
    (4, "Priya Raghunathan", "045-22-8817", "2003-05-09",
     "3307 Marigold Ln, Naperville, IL 60540", "630-555-0118", "praghunathan03@quickmail.com"),
    (5, "Oscar Bellweather", "271-49-6033", "1979-02-26",
     "912 Harlow St, Bangor, ME 04401", "207-555-0173", "obellweather@quickmail.com"),
    (6, "Nadia Osei-Kwame", "588-71-4402", "1986-12-03",
     "5 Winterbourne Rd Apt 3B, Silver Spring, MD 20910", "240-555-0155", "n.oseikwame@quickmail.com"),
]

# --- scores -----------------------------------------------------------------
# (applicant_id, abuse, first_party, third_party, risk_tier, reason_codes)
SCORES = [
    (1, 918, 640, 935, "high",
     "SSN_HEADER_MISMATCH,RAPID_TRADELINE_GROWTH,AUTHORIZED_USER_BOOST,SHARED_DEVICE"),
    (2, 874, 590, 902, "high",
     "SSN_HEADER_MISMATCH,ADDRESS_SHARED_WITH_FLAGGED,THIN_FILE_RAPID_GROWTH"),
    (3, 841, 555, 870, "high",
     "SHARED_PHONE,AUTHORIZED_USER_BOOST,IP_SHARED_WITH_FLAGGED"),
    (4, 402, 310, 430, "medium",
     "THIN_FILE,AUTHORIZED_USER_BOOST,LIMITED_HISTORY"),
    (5, 766, 880, 240, "high",
     "RAPID_LIMIT_STACKING,UTILIZATION_SPIKE,FIRST_PARTY_ABUSE_PATTERN"),
    (6, 538, 300, 610, "medium",
     "SSN_HEADER_MISMATCH,SHORT_CREDIT_HISTORY,ADDRESS_VELOCITY"),
]

# --- SSN verification checks ---------------------------------------------
# Two separate real signals, not one composite:
#   ecbsv_match                — what eCBSV actually returns (SSA match on
#                                SSN + name + DOB). Nothing about issuance.
#   ssn_first_observed         — earliest appearance of the SSN in credit-header
#                                / identity-graph data, which is the signal
#                                SentiLink-style scoring actually uses.
#   dob_consistent_with_header — whether that first-observed date is plausible
#                                for someone born on the claimed DOB.
#
# Note the ring members (1-3) all PASS eCBSV: the SSN and the invented name
# have been reported together long enough for SSA's records to agree. That is
# exactly why a match alone proves very little, and it is the sharper story.
# (applicant_id, ecbsv_match, ssn_first_observed, dob_consistent_with_header, notes)
SSN_CHECKS = [
    (1, 1, "2016-08", 0,
     "SSA returns a match on SSN, name and DOB. But the SSN has no presence in "
     "header data before 2016-08, when the claimed DOB of 1991-03-14 implies "
     "roughly 25 years of prior records. A match with no history is the "
     "signature the score is reacting to."),
    (2, 1, "2015-11", 0,
     "SSA match. No header presence before 2015-11 against a claimed DOB of "
     "1988-07-02 — roughly 27 years unaccounted for."),
    (3, 1, "2016-05", 0,
     "SSA match. No header presence before 2016-05 against a claimed DOB of "
     "1993-11-21. SSN is numerically adjacent to two other numbers first "
     "observed in the same quarter."),
    (4, 1, "2019-09", 1,
     "SSA match. First observed 2019-09, one month after the authorized-user "
     "line was opened — exactly what a 16-year-old's first credit record looks "
     "like. Consistent with the claimed DOB of 2003-05-09."),
    (5, 1, "1997-04", 1,
     "SSA match. Header presence back to 1997-04, consistent with the claimed "
     "DOB of 1979-02-26 and with a file opened in 2004."),
    (6, 1, "2021-10", 0,
     "SSA match. No header presence before 2021-10 against a claimed DOB of "
     "1986-12-03. This is expected for someone who arrived in the US as an "
     "adult: there is no US credit history to find before arrival, and SSA "
     "issues numbers to work-authorized adults routinely. The absence of "
     "history is not by itself evidence that the identity is fabricated."),
]

# --- tradelines -------------------------------------------------------------
# (applicant_id, open_date, ecoa_code, creditor, credit_limit, balance, status)
TRADELINES = [
    # 1 — textbook maturation: piggyback AU line, starter card, then stacking.
    (1, "2022-04-11", AU, "Cascadia Bank Platinum", 15000, 0, "current"),
    (1, "2022-09-02", IND, "Northgate Retail Card", 500, 120, "current"),
    (1, "2023-01-19", IND, "Pinelake CU Secured Card", 300, 0, "closed"),
    (1, "2023-08-05", AU, "Harborline Visa Signature", 22000, 1400, "current"),
    (1, "2024-02-27", IND, "Meridian Auto Finance", 31000, 28700, "current"),
    (1, "2024-06-14", IND, "Cascadia Bank Rewards", 9000, 8850, "current"),
    (1, "2025-01-08", IND, "Sunbelt Personal Loan", 25000, 25000, "current"),
    # 2 — same pattern, same AU host creditor as 1.
    (2, "2022-06-20", AU, "Harborline Visa Signature", 22000, 900, "current"),
    (2, "2023-03-14", IND, "Northgate Retail Card", 700, 340, "current"),
    (2, "2024-01-30", IND, "Cascadia Bank Rewards", 6500, 6200, "current"),
    (2, "2024-11-12", IND, "Sunbelt Personal Loan", 18000, 18000, "current"),
    # 3 — same pattern, already slipping into past_due.
    (3, "2022-05-02", AU, "Cascadia Bank Platinum", 15000, 300, "current"),
    (3, "2023-07-21", IND, "Pinelake CU Secured Card", 500, 0, "closed"),
    (3, "2024-04-09", IND, "Meridian Auto Finance", 24500, 23900, "current"),
    (3, "2025-02-17", IND, "Harborline Visa Signature", 12000, 11400, "past_due"),
    # 4 — real thin file. AU line from a parent at 16, then normal progression,
    #     low utilization throughout. The AU line is the innocent version of the
    #     same signal that looks damning on 1-3.
    (4, "2019-08-15", AU, "First Cascade Family Visa", 8000, 620, "current"),
    (4, "2022-09-01", IND, "Statewide Student Card", 1000, 210, "current"),
    (4, "2024-06-03", IND, "Pinelake CU Auto", 12000, 9400, "current"),
    # 5 — 20 years of real history, then a bust-out run in 2025.
    (5, "2004-03-22", IND, "Ironwood Bank Classic", 4000, 350, "current"),
    (5, "2009-11-04", IND, "Meridian Mortgage", 210000, 96000, "current"),
    (5, "2013-05-30", IND, "Cascadia Bank Rewards", 12000, 1100, "current"),
    (5, "2025-03-12", IND, "Harborline Visa Signature", 25000, 24600, "current"),
    (5, "2025-05-06", IND, "Sunbelt Personal Loan", 40000, 40000, "current"),
    (5, "2025-07-19", IND, "Northgate Retail Card", 6000, 5950, "current"),
    # 6 — short but entirely ordinary credit-building history.
    (6, "2021-10-08", IND, "Newcomer Secured Card", 500, 40, "current"),
    (6, "2022-06-15", IND, "Pinelake CU Credit Builder", 1500, 300, "current"),
    (6, "2023-09-27", IND, "Cascadia Bank Rewards", 4000, 900, "current"),
    (6, "2024-08-19", IND, "Pinelake CU Auto", 18000, 14200, "current"),
]

# --- shared identifiers -----------------------------------------------------
# Stored from both sides so a lookup by either applicant_id finds the link.
# (applicant_id, identifier_type, identifier_value, linked_applicant_id)
# (a, b, type, value, first_seen, last_seen)
# The device and IP sightings are deliberately tight — all three applications
# inside eleven days in August 2025 — because that velocity is far harder to
# explain innocently than the same matches spread over years. The shared
# address spans months, which is the weaker signal of the two and should be
# argued as such.
_LINKS = [
    (1, 2, "address", "1420 Kelso Ave Unit 5, Tampa, FL 33605", "2024-11-02", "2025-08-14"),
    (1, 3, "phone", "813-555-0146", "2025-01-19", "2025-08-11"),
    (1, 2, "device_id", "dv_9f3ac1b8e2", "2025-08-04", "2025-08-15"),
    (1, 3, "device_id", "dv_9f3ac1b8e2", "2025-08-04", "2025-08-12"),
    (2, 3, "device_id", "dv_9f3ac1b8e2", "2025-08-11", "2025-08-15"),
    (1, 2, "ip_address", "198.51.100.77", "2025-08-04", "2025-08-15"),
    (1, 3, "ip_address", "198.51.100.77", "2025-08-04", "2025-08-12"),
    (2, 3, "ip_address", "198.51.100.77", "2025-08-11", "2025-08-15"),
    (2, 3, "email", "riverbendfilings@mailburst.net", "2025-07-28", "2025-08-15"),
]
# 4, 5 and 6 deliberately have no shared identifiers. For 4 and 6 that is the
# single strongest point in their favour; for 5 it is the tell that this is a
# first-party case, not a ring.
SHARED_IDENTIFIERS = [
    row
    for a, b, kind, value, first_seen, last_seen in _LINKS
    for row in (
        (a, kind, value, b, first_seen, last_seen),
        (b, kind, value, a, first_seen, last_seen),
    )
]


# Delinquency written into the profile by (applicant_id, creditor), most
# recent month first. Everything not listed here pays as agreed.
#   3's Harborline is the ring member already unravelling.
#   6 carries a single cured 30-day late, 14 months back — an ordinary human
#   blemish. Manufactured files rarely show sloppy-but-recovered behaviour,
#   so it is quiet evidence that she is real.
PAYMENT_OVERRIDES = {
    (3, "Harborline Visa Signature"): {0: "2", 1: "1"},
    (6, "Pinelake CU Credit Builder"): {14: "1"},
}


def _months_between(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month)


_EXTRA_OVERRIDES: dict = {}


def payment_history_profile(
    applicant_id: int, creditor: str, open_date: str, status: str
) -> str:
    """Build the real Metro 2 field: 24 characters, most recent month first.

    'B' marks months before the account existed, so a young account carries a
    short history and a long one fills the window — which is itself a signal.
    """
    opened = date.fromisoformat(open_date)
    months = max(0, min(24, _months_between(opened, AS_OF)))
    overrides = PAYMENT_OVERRIDES.get(
        (applicant_id, creditor),
        _EXTRA_OVERRIDES.get((applicant_id, creditor), {}),
    )
    profile = [overrides.get(i, "0") for i in range(months)]
    if status == "closed" and months:
        # A closed account stops reporting activity; the months still read as
        # paid, which is what a settled secured card looks like.
        pass
    return "".join(profile) + "B" * (24 - months)


def build(db_path: Path, schema_path: Path, include_eval_cases: bool = True) -> None:
    extra = eval_cases if include_eval_cases else None
    if extra:
        _EXTRA_OVERRIDES.update(extra.payment_overrides())
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(schema_path.read_text())
        applicants = APPLICANTS + (extra.applicants() if extra else [])
        conn.executemany(
            "INSERT INTO applicants (id, name, ssn, claimed_dob, claimed_address,"
            " claimed_phone, claimed_email) VALUES (?, ?, ?, ?, ?, ?, ?)",
            applicants,
        )
        conn.executemany(
            "INSERT INTO scores (applicant_id, abuse_score, first_party_synthetic_score,"
            " third_party_synthetic_score, risk_tier, reason_codes) VALUES (?, ?, ?, ?, ?, ?)",
            SCORES + (extra.scores() if extra else []),
        )
        conn.executemany(
            "INSERT INTO ssn_verification_checks (applicant_id, ecbsv_match,"
            " ssn_first_observed, dob_consistent_with_header, notes)"
            " VALUES (?, ?, ?, ?, ?)",
            SSN_CHECKS + (extra.ssn_checks() if extra else []),
        )
        conn.executemany(
            "INSERT INTO tradelines (applicant_id, account_open_date, ecoa_code,"
            " creditor, credit_limit, balance, status, payment_history_profile)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (*row, payment_history_profile(row[0], row[3], row[1], row[6]))
                for row in TRADELINES + (extra.tradelines() if extra else [])
            ],
        )
        conn.executemany(
            "INSERT INTO shared_identifiers (applicant_id, identifier_type,"
            " identifier_value, linked_applicant_id, first_seen, last_seen)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            SHARED_IDENTIFIERS + (extra.shared_identifiers() if extra else []),
        )
        conn.commit()
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true",
                        help="delete an existing database and rebuild it")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    args = parser.parse_args(argv)

    if args.db.exists():
        if not args.force:
            print(f"{args.db} already exists. Re-run with --force to rebuild.", file=sys.stderr)
            return 1
        args.db.unlink()

    build(args.db, SCHEMA_PATH)
    conn = sqlite3.connect(args.db)
    counts = {
        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("applicants", "tradelines", "shared_identifiers", "audit_log")
    }
    conn.close()
    print(
        f"Seeded {args.db}: {counts['applicants']} applicants "
        f"({len(APPLICANTS)} hand-built + {counts['applicants'] - len(APPLICANTS)} synthesized "
        f"for the eval), {counts['tradelines']} tradelines, "
        f"{counts['shared_identifiers']} shared-identifier rows, "
        f"{counts['audit_log']} audit_log rows."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
