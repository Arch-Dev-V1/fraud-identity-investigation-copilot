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
from pathlib import Path

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
     "SSN_ISSUANCE_MISMATCH,RAPID_TRADELINE_GROWTH,AUTHORIZED_USER_BOOST,SHARED_DEVICE"),
    (2, 874, 590, 902, "high",
     "SSN_ISSUANCE_MISMATCH,ADDRESS_SHARED_WITH_FLAGGED,THIN_FILE_RAPID_GROWTH"),
    (3, 841, 555, 870, "high",
     "SHARED_PHONE,AUTHORIZED_USER_BOOST,IP_SHARED_WITH_FLAGGED"),
    (4, 402, 310, 430, "medium",
     "THIN_FILE,AUTHORIZED_USER_BOOST,LIMITED_HISTORY"),
    (5, 766, 880, 240, "high",
     "RAPID_LIMIT_STACKING,UTILIZATION_SPIKE,FIRST_PARTY_ABUSE_PATTERN"),
    (6, 538, 300, 610, "medium",
     "SSN_ISSUANCE_MISMATCH,SHORT_CREDIT_HISTORY,ADDRESS_VELOCITY"),
]

# --- SSN issuance checks ----------------------------------------------------
# (applicant_id, dob_matches_issuance, issuance_period, notes)
SSN_CHECKS = [
    (1, 0, "2016-2018",
     "No SSA enumeration record before 2016. Claimed DOB 1991-03-14 predates the "
     "issuance window by roughly 25 years."),
    (2, 0, "2015-2017",
     "No SSA enumeration record before 2015. Claimed DOB 1988-07-02 predates the "
     "issuance window by roughly 27 years."),
    (3, 0, "2016-2018",
     "No SSA enumeration record before 2016. Claimed DOB 1993-11-21 predates the "
     "issuance window by roughly 23 years. Number is numerically adjacent to two "
     "other numbers seen on flagged applications."),
    (4, 1, "2003-2004",
     "Issuance window consistent with claimed DOB 2003-05-09 (enumeration at birth)."),
    (5, 1, "1979-1980",
     "Issuance window consistent with claimed DOB 1979-02-26 (enumeration at birth)."),
    (6, 0, "2021",
     "Issued 2021 to an applicant recorded as an adult; claimed DOB 1986-12-03. "
     "Adult issuance is routine for work-authorized arrivals and for people who "
     "were never enumerated at birth. A mismatch here is not by itself evidence "
     "that the identity is fabricated."),
]

# --- tradelines -------------------------------------------------------------
# (applicant_id, open_date, ecoa_code, creditor, credit_limit, balance, status)
TRADELINES = [
    # 1 — textbook maturation: piggyback AU line, starter card, then stacking.
    (1, "2022-04-11", "authorized_user", "Cascadia Bank Platinum", 15000, 0, "current"),
    (1, "2022-09-02", "individual", "Northgate Retail Card", 500, 120, "current"),
    (1, "2023-01-19", "individual", "Pinelake CU Secured Card", 300, 0, "closed"),
    (1, "2023-08-05", "authorized_user", "Harborline Visa Signature", 22000, 1400, "current"),
    (1, "2024-02-27", "individual", "Meridian Auto Finance", 31000, 28700, "current"),
    (1, "2024-06-14", "individual", "Cascadia Bank Rewards", 9000, 8850, "current"),
    (1, "2025-01-08", "individual", "Sunbelt Personal Loan", 25000, 25000, "current"),
    # 2 — same pattern, same AU host creditor as 1.
    (2, "2022-06-20", "authorized_user", "Harborline Visa Signature", 22000, 900, "current"),
    (2, "2023-03-14", "individual", "Northgate Retail Card", 700, 340, "current"),
    (2, "2024-01-30", "individual", "Cascadia Bank Rewards", 6500, 6200, "current"),
    (2, "2024-11-12", "individual", "Sunbelt Personal Loan", 18000, 18000, "current"),
    # 3 — same pattern, already slipping into past_due.
    (3, "2022-05-02", "authorized_user", "Cascadia Bank Platinum", 15000, 300, "current"),
    (3, "2023-07-21", "individual", "Pinelake CU Secured Card", 500, 0, "closed"),
    (3, "2024-04-09", "individual", "Meridian Auto Finance", 24500, 23900, "current"),
    (3, "2025-02-17", "individual", "Harborline Visa Signature", 12000, 11400, "past_due"),
    # 4 — real thin file. AU line from a parent at 16, then normal progression,
    #     low utilization throughout. The AU line is the innocent version of the
    #     same signal that looks damning on 1-3.
    (4, "2019-08-15", "authorized_user", "First Cascade Family Visa", 8000, 620, "current"),
    (4, "2022-09-01", "individual", "Statewide Student Card", 1000, 210, "current"),
    (4, "2024-06-03", "individual", "Pinelake CU Auto", 12000, 9400, "current"),
    # 5 — 20 years of real history, then a bust-out run in 2025.
    (5, "2004-03-22", "individual", "Ironwood Bank Classic", 4000, 350, "current"),
    (5, "2009-11-04", "individual", "Meridian Mortgage", 210000, 96000, "current"),
    (5, "2013-05-30", "individual", "Cascadia Bank Rewards", 12000, 1100, "current"),
    (5, "2025-03-12", "individual", "Harborline Visa Signature", 25000, 24600, "current"),
    (5, "2025-05-06", "individual", "Sunbelt Personal Loan", 40000, 40000, "current"),
    (5, "2025-07-19", "individual", "Northgate Retail Card", 6000, 5950, "current"),
    # 6 — short but entirely ordinary credit-building history.
    (6, "2021-10-08", "individual", "Newcomer Secured Card", 500, 40, "current"),
    (6, "2022-06-15", "individual", "Pinelake CU Credit Builder", 1500, 300, "current"),
    (6, "2023-09-27", "individual", "Cascadia Bank Rewards", 4000, 900, "current"),
    (6, "2024-08-19", "individual", "Pinelake CU Auto", 18000, 14200, "current"),
]

# --- shared identifiers -----------------------------------------------------
# Stored from both sides so a lookup by either applicant_id finds the link.
# (applicant_id, identifier_type, identifier_value, linked_applicant_id)
_LINKS = [
    (1, 2, "address", "1420 Kelso Ave Unit 5, Tampa, FL 33605"),
    (1, 3, "phone", "813-555-0146"),
    (1, 2, "device_id", "dv_9f3ac1b8e2"),
    (1, 3, "device_id", "dv_9f3ac1b8e2"),
    (2, 3, "device_id", "dv_9f3ac1b8e2"),
    (1, 2, "ip_address", "198.51.100.77"),
    (1, 3, "ip_address", "198.51.100.77"),
    (2, 3, "ip_address", "198.51.100.77"),
    (2, 3, "email", "riverbendfilings@mailburst.net"),
]
# 4, 5 and 6 deliberately have no shared identifiers. For 4 and 6 that is the
# single strongest point in their favour; for 5 it is the tell that this is a
# first-party case, not a ring.
SHARED_IDENTIFIERS = [
    row
    for a, b, kind, value in _LINKS
    for row in ((a, kind, value, b), (b, kind, value, a))
]


def build(db_path: Path, schema_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(schema_path.read_text())
        conn.executemany(
            "INSERT INTO applicants (id, name, ssn, claimed_dob, claimed_address,"
            " claimed_phone, claimed_email) VALUES (?, ?, ?, ?, ?, ?, ?)",
            APPLICANTS,
        )
        conn.executemany(
            "INSERT INTO scores (applicant_id, abuse_score, first_party_synthetic_score,"
            " third_party_synthetic_score, risk_tier, reason_codes) VALUES (?, ?, ?, ?, ?, ?)",
            SCORES,
        )
        conn.executemany(
            "INSERT INTO ssn_issuance_checks (applicant_id, dob_matches_issuance,"
            " issuance_period, notes) VALUES (?, ?, ?, ?)",
            SSN_CHECKS,
        )
        conn.executemany(
            "INSERT INTO tradelines (applicant_id, account_open_date, ecoa_code,"
            " creditor, credit_limit, balance, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            TRADELINES,
        )
        conn.executemany(
            "INSERT INTO shared_identifiers (applicant_id, identifier_type,"
            " identifier_value, linked_applicant_id) VALUES (?, ?, ?, ?)",
            SHARED_IDENTIFIERS,
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
    print(
        f"Seeded {args.db}: {len(APPLICANTS)} applicants, {len(TRADELINES)} tradelines, "
        f"{len(SHARED_IDENTIFIERS)} shared-identifier rows, 0 audit_log rows."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
