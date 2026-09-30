"""The provider-integration service — HTTP transport over provider_api.lookups.

Endpoints take an ``applicant_id`` because that is what our own system of
record keys on. Each response carries the attribute-shaped payload a real
vendor would have received under ``request``, so the provider contract stays
visible rather than implied.

    uvicorn provider_api.main:app --port 8000
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException

from . import lookups

DB_PATH = Path(
    os.environ.get(
        "CASES_DB", Path(__file__).resolve().parent.parent / "db" / "cases.db"
    )
)

app = FastAPI(
    title="Synthetic Identity Provider Gateway (mock)",
    description=(
        "Stands in for the vendor APIs a lender would call — SentiLink, Socure "
        "and friends are all HTTP services taking identity attributes. All "
        "data here is fabricated for the POC."
    ),
    version="1.0.0",
)


def _run(lookup: Callable, applicant_id: int) -> dict[str, Any]:
    if not DB_PATH.exists():
        raise HTTPException(503, f"No case database at {DB_PATH}. Run python db/seed.py.")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        return lookup(conn, applicant_id)
    except lookups.LookupNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    finally:
        conn.close()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "database": DB_PATH.exists()}


@app.get("/v1/applicants/{applicant_id}/ssn-verification")
def ssn_verification(applicant_id: int) -> dict[str, Any]:
    return _run(lookups.ssn_verification, applicant_id)


@app.get("/v1/applicants/{applicant_id}/credit-trajectory")
def credit_trajectory(applicant_id: int) -> dict[str, Any]:
    return _run(lookups.credit_trajectory, applicant_id)


@app.get("/v1/applicants/{applicant_id}/authorized-user-history")
def authorized_user_history(applicant_id: int) -> dict[str, Any]:
    return _run(lookups.authorized_user_history, applicant_id)


@app.get("/v1/applicants/{applicant_id}/shared-identifiers")
def shared_identifiers(applicant_id: int) -> dict[str, Any]:
    return _run(lookups.shared_identifiers, applicant_id)
