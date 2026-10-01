"""The synthesized half of the case set, for the eval.

The six applicants in seed.py are hand-built archetypes. These nineteen are
variations on them, generated from explicit specs so each case's dials — the
header gap, the authorized-user boost, the velocity span, the payment profile —
are visible in one line instead of buried in rows of literal data.

They are synthesized, and that is a real limitation: there is no production
traffic to sample, because every applicant in this project is fabricated by
design. What anchors them is that each one is a variation on an archetype that
was reviewed first, with a stated labeling policy (see LABEL_POLICY) rather
than per-case intuition.

Expected labels live in evals/cases.py, not here: this module generates data,
the eval owns the ground truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from provider_api import metro2

LABEL_POLICY = """\
high   — the header gap is inconsistent with the claimed DOB with no benign
         cause recorded, AND either a ring link at tight velocity (one
         identifier across 3+ applicants inside ~30 days) or an
         authorized-user boost followed by rapid stacking to near-full
         utilization.
medium — signals are present but each has a plausible innocent reading, or
         they conflict (a gap with a cured delinquency; a shared identifier
         over a span long enough to be a building or a carrier).
low    — the header is consistent with the claimed DOB, OR the gap has an
         explicit benign cause recorded, OR there are no links and the
         trajectory and payment history are ordinary.
"""


@dataclass
class Spec:
    id: int
    name: str
    dob: str
    ssn: str
    address: str
    phone: str
    email: str
    scores: tuple[int, int, int, str, str]      # abuse, first-party, third-party, tier, codes
    first_observed: str
    dob_consistent: bool
    notes: str
    pattern: str                                 # ramp | organic | bustout | thin
    ecbsv_match: bool = True
    au: list[tuple[str, str, int]] = field(default_factory=list)   # open, creditor, limit
    delinquency: dict[str, dict[int, str]] = field(default_factory=dict)


# --- tradeline patterns ------------------------------------------------------

def _tl(applicant, open_date, ecoa, creditor, limit, balance, status):
    return (applicant, open_date, ecoa, creditor, limit, balance, status)


def _build_tradelines(spec: Spec) -> list[tuple]:
    """Turn a pattern name into Metro 2 rows."""
    rows: list[tuple] = []
    for open_date, creditor, limit in spec.au:
        rows.append(_tl(spec.id, open_date, metro2.ECOA_AUTHORIZED_USER, creditor, limit,
                        int(limit * 0.04), "current"))

    if spec.pattern == "ramp":
        # Manufactured: starter card, then stacking to near-full utilization.
        rows += [
            _tl(spec.id, "2022-10-04", metro2.ECOA_INDIVIDUAL, "Northgate Retail Card", 600, 180, "current"),
            _tl(spec.id, "2024-03-18", metro2.ECOA_INDIVIDUAL, "Meridian Auto Finance", 27000, 25600, "current"),
            _tl(spec.id, "2024-09-25", metro2.ECOA_INDIVIDUAL, "Cascadia Bank Rewards", 8000, 7750, "current"),
            _tl(spec.id, "2025-02-11", metro2.ECOA_INDIVIDUAL, "Sunbelt Personal Loan", 22000, 22000, "current"),
        ]
    elif spec.pattern == "organic":
        rows += [
            _tl(spec.id, "2016-05-12", metro2.ECOA_INDIVIDUAL, "Ironwood Bank Classic", 3500, 410, "current"),
            _tl(spec.id, "2019-08-20", metro2.ECOA_INDIVIDUAL, "Pinelake CU Auto", 16000, 5200, "current"),
            _tl(spec.id, "2023-01-14", metro2.ECOA_INDIVIDUAL, "Cascadia Bank Rewards", 7500, 1150, "current"),
        ]
    elif spec.pattern == "bustout":
        rows += [
            _tl(spec.id, "2006-07-19", metro2.ECOA_INDIVIDUAL, "Ironwood Bank Classic", 4500, 300, "current"),
            _tl(spec.id, "2012-02-28", metro2.ECOA_INDIVIDUAL, "Meridian Mortgage", 185000, 71000, "current"),
            _tl(spec.id, "2025-04-02", metro2.ECOA_INDIVIDUAL, "Harborline Visa Signature", 24000, 23500, "current"),
            _tl(spec.id, "2025-06-16", metro2.ECOA_INDIVIDUAL, "Sunbelt Personal Loan", 35000, 35000, "current"),
        ]
    elif spec.pattern == "thin":
        rows += [
            _tl(spec.id, "2022-11-07", metro2.ECOA_INDIVIDUAL, "Statewide Student Card", 1200, 260, "current"),
            _tl(spec.id, "2024-05-21", metro2.ECOA_INDIVIDUAL, "Pinelake CU Credit Builder", 2000, 480, "current"),
        ]
    else:  # pragma: no cover
        raise ValueError(f"unknown pattern {spec.pattern!r}")
    return rows


# --- the specs ---------------------------------------------------------------
# Ring B (ids 7-9): a second ring, linked by a shared email and IP inside six
# days. Ring C (ids 11-12): a pair sharing an address and device over nine days.
_A = "Apt"
SPECS: list[Spec] = [
    # ---------- expected high ----------
    Spec(7, "Keshaun Vrabel", "1990-06-17", "641-02-7733",
         f"88 Tidewater Row {_A} 2, Mobile, AL 36604", "251-555-0133", "k.vrabel@mailburst.net",
         (906, 620, 925, "high", "SSN_HEADER_MISMATCH,AUTHORIZED_USER_BOOST,SHARED_EMAIL,RAPID_TRADELINE_GROWTH"),
         "2017-03", False,
         "SSA match. No header presence before 2017-03 against a claimed DOB of 1990-06-17.",
         "ramp", au=[("2022-05-16", "Cascadia Bank Platinum", 14000)]),
    Spec(8, "Marlee Ostrowski", "1987-01-29", "641-02-7718",
         f"88 Tidewater Row {_A} 2, Mobile, AL 36604", "251-555-0171", "m.ostrowski@mailburst.net",
         (883, 601, 911, "high", "SSN_HEADER_MISMATCH,SHARED_EMAIL,IP_SHARED_WITH_FLAGGED"),
         "2016-09", False,
         "SSA match. No header presence before 2016-09 against a claimed DOB of 1987-01-29.",
         "ramp", au=[("2022-08-02", "Harborline Visa Signature", 19000)]),
    Spec(9, "Donte Kirkbride", "1992-10-05", "641-02-7746",
         "17 Belgrave Ct, Theodore, AL 36582", "251-555-0188", "d.kirkbride@mailburst.net",
         (861, 572, 889, "high", "SSN_HEADER_MISMATCH,SHARED_DEVICE,AUTHORIZED_USER_BOOST"),
         "2017-07", False,
         "SSA match. No header presence before 2017-07 against a claimed DOB of 1992-10-05.",
         "ramp", au=[("2022-06-29", "Cascadia Bank Platinum", 14000)]),
    Spec(10, "Sylvan Brightmore", "1985-04-22", "702-55-3390",
         "4410 Lacebark Dr, Boise, ID 83709", "208-555-0164", "s.brightmore@quickmail.com",
         (848, 640, 862, "high", "SSN_HEADER_MISMATCH,AUTHORIZED_USER_BOOST,UTILIZATION_SPIKE"),
         "2019-02", False,
         "SSA match. No header presence before 2019-02 against a claimed DOB of 1985-04-22 — "
         "roughly 34 years unaccounted for.",
         "ramp", au=[("2021-11-09", "First Cascade Family Visa", 17000)]),
    Spec(11, "Orlaith Fennimore", "1989-12-11", "518-63-2204",
         f"9 Harrowgate Pl {_A} 7, Dayton, OH 45402", "937-555-0119", "o.fennimore@mailburst.net",
         (877, 588, 902, "high", "SSN_HEADER_MISMATCH,ADDRESS_SHARED_WITH_FLAGGED,SHARED_DEVICE"),
         "2016-11", False,
         "SSA match. No header presence before 2016-11 against a claimed DOB of 1989-12-11.",
         "ramp", au=[("2022-07-14", "Harborline Visa Signature", 20000)]),
    Spec(12, "Rhett Calloway-Brees", "1991-08-30", "518-63-2241",
         f"9 Harrowgate Pl {_A} 7, Dayton, OH 45402", "937-555-0142", "r.calloway@mailburst.net",
         (855, 566, 884, "high", "SSN_HEADER_MISMATCH,ADDRESS_SHARED_WITH_FLAGGED,SHARED_DEVICE"),
         "2017-01", False,
         "SSA match. No header presence before 2017-01 against a claimed DOB of 1991-08-30.",
         "ramp", au=[("2022-09-08", "Cascadia Bank Platinum", 15000)]),
    # ---------- expected low ----------
    Spec(13, "Imogen Hartsfield", "2004-02-18", "061-44-9902",
         "77 Larkmead Ln, Madison, WI 53703", "608-555-0127", "i.hartsfield@quickmail.com",
         (388, 295, 412, "medium", "THIN_FILE,AUTHORIZED_USER_BOOST,LIMITED_HISTORY"),
         "2020-06", True,
         "SSA match. First observed 2020-06, shortly after the authorized-user line opened — "
         "consistent with the claimed DOB of 2004-02-18.",
         "thin", au=[("2020-05-11", "First Cascade Family Visa", 7000)]),
    Spec(14, "Alton Pemberton", "1958-09-03", "233-18-5571",
         "612 Quarry Bend Rd, Scranton, PA 18503", "570-555-0198", "a.pemberton@quickmail.com",
         (301, 240, 318, "low", "SHORT_RECENT_ACTIVITY"),
         "1976-05", True,
         "SSA match. Header presence back to 1976-05, consistent with the claimed DOB of 1958-09-03.",
         "organic", delinquency={"Pinelake CU Auto": {19: "1"}}),
    Spec(15, "Tendai Mushonga", "1984-07-14", "594-80-1163",
         f"31 Pennyroyal Way {_A} 1C, Columbus, OH 43215", "614-555-0156", "t.mushonga@quickmail.com",
         (556, 318, 627, "medium", "SSN_HEADER_MISMATCH,SHORT_CREDIT_HISTORY"),
         "2020-08", False,
         "SSA match. No header presence before 2020-08 against a claimed DOB of 1984-07-14. "
         "Adult issuance is routine for work-authorized arrivals and for people never "
         "enumerated at birth. The absence of history is not by itself evidence that the "
         "identity is fabricated.",
         "thin"),
    Spec(16, "Bernadette Oyelaran", "1979-11-26", "447-29-6680",
         "1208 Ashcombe St, Raleigh, NC 27601", "919-555-0175", "b.oyelaran@quickmail.com",
         (412, 330, 436, "medium", "AUTHORIZED_USER_REMOVED,SHORT_RECENT_ACTIVITY"),
         "1998-02", True,
         "SSA match. Header presence back to 1998-02, consistent with the claimed DOB of "
         "1979-11-26. A joint line closed in 2023.",
         "organic"),
    Spec(17, "Desmond Achterberg", "2002-06-08", "095-71-3328",
         "54 Kettleman Ave, Provo, UT 84601", "801-555-0149", "d.achterberg@quickmail.com",
         (356, 282, 377, "low", "THIN_FILE,LIMITED_HISTORY"),
         "2002-09", True,
         "SSA match. Header presence from 2002-09, consistent with enumeration at birth "
         "against the claimed DOB of 2002-06-08.",
         "thin"),
    Spec(18, "Corwin Stapleton", "1974-03-19", "318-60-4417",
         "903 Verdant Hollow, Billings, MT 59101", "406-555-0186", "c.stapleton@quickmail.com",
         (741, 865, 232, "high", "RAPID_LIMIT_STACKING,UTILIZATION_SPIKE,FIRST_PARTY_ABUSE_PATTERN"),
         "1993-08", True,
         "SSA match. Header presence back to 1993-08, consistent with the claimed DOB of "
         "1974-03-19.",
         "bustout"),
    # ---------- expected medium ----------
    Spec(19, "Yusuf Benkiran", "1996-05-02", "677-12-8805",
         "22 Coppersmith Row, Fresno, CA 93721", "559-555-0131", "y.benkiran@quickmail.com",
         (604, 402, 651, "medium", "SSN_HEADER_MISMATCH,SHORT_CREDIT_HISTORY"),
         "2004-04", False,
         "SSA match. First observed 2004-04 against a claimed DOB of 1996-05-02 — an eight-year "
         "gap, which is short enough to fit late enumeration or a thin early record, and short "
         "enough that it is not the decades-long absence a built identity shows.",
         "organic"),
    Spec(20, "Marisol Trevejo", "1983-01-15", "409-77-2259",
         f"1420 Kelso Ave {_A} 9, Tampa, FL 33605", "813-555-0121", "m.trevejo@quickmail.com",
         (588, 361, 640, "medium", "ADDRESS_SHARED_WITH_FLAGGED"),
         "2001-10", True,
         "SSA match. Header presence back to 2001-10, consistent with the claimed DOB of "
         "1983-01-15.",
         "organic"),
    Spec(21, "Ignatius Rowlandson", "1981-09-27", "556-34-7791",
         "305 Tallowwood Dr, Mesa, AZ 85201", "480-555-0193", "i.rowlandson@quickmail.com",
         (631, 430, 668, "medium", "SSN_HEADER_MISMATCH,AUTHORIZED_USER_BOOST,SHARED_PHONE"),
         "2019-05", False,
         "SSA match. No header presence before 2019-05 against a claimed DOB of 1981-09-27. "
         "The applicant reports arriving in the US as an adult; adult issuance is routine in "
         "that case.",
         "organic", au=[("2021-03-22", "First Cascade Family Visa", 9000)]),
    Spec(22, "Arabella Nkemdirim", "1988-04-11", "612-05-9948",
         "66 Hollowbrook Ct, Augusta, GA 30901", "706-555-0168", "a.nkemdirim@quickmail.com",
         (617, 418, 659, "medium", "SSN_HEADER_MISMATCH,PAYMENT_IRREGULARITY"),
         "2018-12", False,
         "SSA match. No header presence before 2018-12 against a claimed DOB of 1988-04-11.",
         "organic", delinquency={"Cascadia Bank Rewards": {9: "2", 10: "1"}}),
    Spec(23, "Thaddeus Quintrell", "1977-02-06", "284-91-3376",
         "19 Gravelly Point Rd, Norfolk, VA 23510", "757-555-0152", "t.quintrell@quickmail.com",
         (572, 350, 618, "medium", "SHARED_DEVICE"),
         "1995-07", True,
         "SSA match. Header presence back to 1995-07, consistent with the claimed DOB of "
         "1977-02-06.",
         "organic"),
    Spec(24, "Priyanka Vellaisamy", "1993-07-23", "731-46-5520",
         "840 Juniper Mill Way, Plano, TX 75023", "972-555-0137", "p.vellaisamy@quickmail.com",
         (648, 455, 682, "medium", "SSN_HEADER_MISMATCH,AUTHORIZED_USER_BOOST"),
         "2005-09", False,
         "SSA match. First observed 2005-09 against a claimed DOB of 1993-07-23 — a twelve-year "
         "gap with no benign cause recorded either way.",
         "organic", au=[("2020-04-17", "First Cascade Family Visa", 11000)]),
    Spec(25, "Emeka Oduya", "1986-10-30", "408-23-7714",
         f"7 Saltmarsh Crescent {_A} 4B, Newark, NJ 07102", "973-555-0145", "e.oduya@quickmail.com",
         (595, 372, 644, "medium", "IP_SHARED_WITH_FLAGGED,SHORT_CREDIT_HISTORY"),
         "2004-01", True,
         "SSA match. Header presence back to 2004-01, consistent with the claimed DOB of "
         "1986-10-30.",
         "organic"),
]

# --- links: (a, b, type, value, first_seen, last_seen) ----------------------
# Ring B and Ring C are tight. Everything in the medium band is deliberately
# wide — long enough to read as a shared building, a recycled number or a
# carrier range rather than one operator.
LINKS: list[tuple] = [
    # Ring B — email + IP across three applicants in six days
    (7, 8, "email", "tidewaterfilings@mailburst.net", "2025-08-19", "2025-08-25"),
    (7, 9, "email", "tidewaterfilings@mailburst.net", "2025-08-19", "2025-08-24"),
    (8, 9, "email", "tidewaterfilings@mailburst.net", "2025-08-21", "2025-08-25"),
    (7, 8, "ip_address", "203.0.113.41", "2025-08-19", "2025-08-25"),
    (7, 9, "ip_address", "203.0.113.41", "2025-08-19", "2025-08-24"),
    (8, 9, "ip_address", "203.0.113.41", "2025-08-21", "2025-08-25"),
    (7, 8, "address", f"88 Tidewater Row {_A} 2, Mobile, AL 36604", "2024-12-03", "2025-08-25"),
    (8, 9, "device_id", "dv_4b71e0c9af", "2025-08-21", "2025-08-25"),
    # Ring C — address + device across a pair in nine days
    (11, 12, "address", f"9 Harrowgate Pl {_A} 7, Dayton, OH 45402", "2025-07-30", "2025-08-08"),
    (11, 12, "device_id", "dv_e82c5d1174", "2025-07-30", "2025-08-08"),
    # Ambiguous middles — wide spans, innocent readings available
    (20, 1, "address", "1420 Kelso Ave Unit 5, Tampa, FL 33605", "2024-02-11", "2025-05-04"),
    (21, 14, "phone", "570-555-0198", "2023-11-08", "2025-06-19"),
    (23, 10, "device_id", "dv_1f90b73c25", "2024-10-22", "2025-07-15"),
    (25, 15, "ip_address", "198.51.100.212", "2024-06-05", "2025-06-28"),
    (25, 19, "ip_address", "198.51.100.212", "2024-09-14", "2025-07-02"),
]


def applicants() -> list[tuple]:
    return [(s.id, s.name, s.ssn, s.dob, s.address, s.phone, s.email) for s in SPECS]


def scores() -> list[tuple]:
    return [(s.id, *s.scores) for s in SPECS]


def ssn_checks() -> list[tuple]:
    return [(s.id, int(s.ecbsv_match), s.first_observed, int(s.dob_consistent), s.notes)
            for s in SPECS]


def tradelines() -> list[tuple]:
    rows: list[tuple] = []
    for spec in SPECS:
        rows += _build_tradelines(spec)
    return rows


def payment_overrides() -> dict:
    return {
        (spec.id, creditor): months
        for spec in SPECS
        for creditor, months in spec.delinquency.items()
    }


def shared_identifiers() -> list[tuple]:
    return [
        row
        for a, b, kind, value, first_seen, last_seen in LINKS
        for row in ((a, kind, value, b, first_seen, last_seen),
                    (b, kind, value, a, first_seen, last_seen))
    ]
