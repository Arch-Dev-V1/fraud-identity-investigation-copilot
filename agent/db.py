"""SQLite access. The UI never imports this directly — it goes through
``agent``'s public surface, so this stays the single place that touches the
database file.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "db" / "cases.db"


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"No case database at {path}. Run `python db/seed.py` first."
        )
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def list_cases(db_path: Path | None = None) -> list[dict]:
    """The flagged-case feed, worst score first."""
    conn = connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT a.id, a.name, s.abuse_score, s.risk_tier, s.reason_codes,
                   (SELECT COUNT(*) FROM audit_log al WHERE al.applicant_id = a.id)
                       AS memo_count,
                   (SELECT al.analyst_decision FROM audit_log al
                     WHERE al.applicant_id = a.id
                     ORDER BY al.created_at DESC, al.id DESC LIMIT 1)
                       AS latest_decision
              FROM applicants a
              JOIN scores s ON s.applicant_id = a.id
             ORDER BY s.abuse_score DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_case(applicant_id: int, db_path: Path | None = None) -> dict:
    """Everything the agent is told up front: the applicant and its score."""
    conn = connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT a.id, a.name, a.ssn, a.claimed_dob, a.claimed_address,
                   a.claimed_phone, a.claimed_email, s.abuse_score,
                   s.first_party_synthetic_score, s.third_party_synthetic_score,
                   s.risk_tier, s.reason_codes
              FROM applicants a
              JOIN scores s ON s.applicant_id = a.id
             WHERE a.id = ?
            """,
            (applicant_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"No such applicant: {applicant_id}")
        return dict(row)
    finally:
        conn.close()


def write_memo(
    applicant_id: int,
    tool_calls_made: str,
    case_memo: str,
    confidence_level: str,
    db_path: Path | None = None,
) -> int:
    """The agent's only write. ``analyst_decision`` is left NULL on purpose —
    the agent has no way to set it, and no tool that could."""
    conn = connect(db_path)
    try:
        cur = conn.execute(
            """
            INSERT INTO audit_log (applicant_id, tool_calls_made, case_memo,
                                   confidence_level, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (applicant_id, tool_calls_made, case_memo, confidence_level, _utcnow()),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def get_memo(audit_log_id: int, db_path: Path | None = None) -> dict | None:
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM audit_log WHERE id = ?", (audit_log_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def latest_memo(applicant_id: int, db_path: Path | None = None) -> dict | None:
    conn = connect(db_path)
    try:
        row = conn.execute(
            """SELECT * FROM audit_log WHERE applicant_id = ?
               ORDER BY created_at DESC, id DESC LIMIT 1""",
            (applicant_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


VALID_DECISIONS = ("approved", "rejected", "escalated")


def record_analyst_decision(
    audit_log_id: int,
    decision: str,
    notes: str | None = None,
    db_path: Path | None = None,
) -> None:
    """Called only from the analyst's button in the UI. This is the one code
    path in the project that can set ``analyst_decision``."""
    if decision not in VALID_DECISIONS:
        raise ValueError(f"decision must be one of {VALID_DECISIONS}, got {decision!r}")
    conn = connect(db_path)
    try:
        cur = conn.execute(
            """UPDATE audit_log
                  SET analyst_decision = ?, analyst_notes = ?, decided_at = ?
                WHERE id = ?""",
            (decision, notes, _utcnow(), audit_log_id),
        )
        if cur.rowcount == 0:
            raise ValueError(f"No audit_log row with id {audit_log_id}")
        conn.commit()
    finally:
        conn.close()
