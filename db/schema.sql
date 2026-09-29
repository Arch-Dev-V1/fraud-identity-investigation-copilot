-- Synthetic Identity Investigation Copilot — mock data schema (SQLite)
-- All data in these tables is fabricated for the POC. Field shapes are
-- modeled on real published formats so the demo holds up: the scores
-- table mirrors SentiLink's published Synthetic Score structure, and
-- the tradelines table mirrors real fields from Metro 2, the actual
-- industry-standard format lenders use to report accounts to bureaus.

-- One row per fabricated applicant.
CREATE TABLE applicants (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    ssn             TEXT NOT NULL,
    claimed_dob     TEXT NOT NULL,
    claimed_address TEXT,
    claimed_phone   TEXT,
    claimed_email   TEXT     -- real scoring providers take email as an input
);

-- The initial flag that starts an investigation.
-- Shape modeled on SentiLink's real Synthetic Score: 0-999,
-- split into first-party / third-party / composite abuse score,
-- with a risk tier and short reason codes.
CREATE TABLE scores (
    applicant_id                 INTEGER PRIMARY KEY REFERENCES applicants(id),
    abuse_score                  INTEGER NOT NULL,       -- 0-999
    first_party_synthetic_score  INTEGER NOT NULL,       -- 0-999
    third_party_synthetic_score  INTEGER NOT NULL,       -- 0-999
    risk_tier                    TEXT NOT NULL,           -- 'low' | 'medium' | 'high'
    reason_codes                 TEXT NOT NULL            -- e.g. "SSN_ISSUANCE_MISMATCH,RAPID_TRADELINE_GROWTH"
);

-- Mock stand-in for a real eCBSV-style check: does the claimed
-- birthdate line up with how/when this SSN was actually issued.
CREATE TABLE ssn_issuance_checks (
    applicant_id            INTEGER PRIMARY KEY REFERENCES applicants(id),
    dob_matches_issuance    INTEGER NOT NULL,   -- 0 or 1
    issuance_period         TEXT,               -- e.g. "2016-2018"
    notes                   TEXT
);

-- Credit account history. Field shapes modeled on real Metro 2
-- base-segment fields. ecoa_code is the field that would capture
-- an "authorized user" credit-boost relationship in a real report.
CREATE TABLE tradelines (
    id                INTEGER PRIMARY KEY,
    applicant_id      INTEGER NOT NULL REFERENCES applicants(id),
    account_open_date TEXT NOT NULL,
    ecoa_code         TEXT NOT NULL,   -- 'individual' | 'joint' | 'authorized_user'
    creditor          TEXT NOT NULL,
    credit_limit      INTEGER,
    balance           INTEGER,
    status            TEXT             -- 'current' | 'past_due' | 'closed'
);

-- Signals shared across applicants — the "does this phone/address/
-- device/email/IP also show up on other flagged applications" lookup.
-- Fraud rings can invent names and SSNs cheaply but tend to reuse an
-- email or an internet connection, so those are often the strongest links.
-- ip_address lives here only (not on applicants): it describes where an
-- application came from, not something the person has.
-- Matching is exact-match only; near-matches (john1@ vs john2@) are out of scope.
CREATE TABLE shared_identifiers (
    id                  INTEGER PRIMARY KEY,
    applicant_id        INTEGER NOT NULL REFERENCES applicants(id),
    identifier_type     TEXT NOT NULL,   -- 'phone' | 'address' | 'device_id' | 'email' | 'ip_address'
    identifier_value    TEXT NOT NULL,
    linked_applicant_id INTEGER REFERENCES applicants(id)
);

-- The audit trail. Every investigation writes one row here —
-- this is where the "human must approve" guardrail is enforced:
-- analyst_decision stays NULL until a person actually sets it.
CREATE TABLE audit_log (
    id                INTEGER PRIMARY KEY,
    applicant_id      INTEGER NOT NULL REFERENCES applicants(id),
    tool_calls_made   TEXT NOT NULL,     -- JSON list of {tool, input, output, timestamp}
    case_memo         TEXT NOT NULL,
    confidence_level  TEXT NOT NULL,     -- 'low' | 'medium' | 'high'
    analyst_decision  TEXT,              -- NULL until a human acts: 'approved' | 'rejected' | 'escalated'
    analyst_notes     TEXT,
    created_at        TEXT DEFAULT CURRENT_TIMESTAMP,
    decided_at        TEXT
);

CREATE INDEX idx_tradelines_applicant ON tradelines(applicant_id, account_open_date);
CREATE INDEX idx_shared_identifiers_applicant ON shared_identifiers(applicant_id);
CREATE INDEX idx_audit_log_applicant ON audit_log(applicant_id, created_at);
