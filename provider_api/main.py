"""The provider-integration service — HTTP transport over provider_api.lookups.

Endpoints take an ``applicant_id`` because that is what our own system of
record keys on. Each response carries the attribute-shaped payload a real
vendor would have received under ``request``, so the provider contract stays
visible rather than implied.

    uvicorn provider_api.main:app --port 8000
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response

from . import lookups

DB_PATH = Path(
    os.environ.get(
        "CASES_DB", Path(__file__).resolve().parent.parent / "db" / "cases.db"
    )
)

# Request tracing, off by default.
#   PROVIDER_API_TRACE=1      one line per request: method, path, status, ms, size
#   PROVIDER_API_TRACE=body   the same, plus the pretty-printed response body
#
# Off by default deliberately: these bodies carry names, SSNs and addresses.
# They are fabricated here, but a gateway that logs provider responses in full
# is not something you would ship, so it stays opt-in.
TRACE = os.environ.get("PROVIDER_API_TRACE", "").strip().lower()
TRACE_BODY = TRACE in ("body", "full", "2")
TRACE_ON = TRACE_BODY or TRACE in ("1", "true", "yes", "on")

app = FastAPI(
    title="Synthetic Identity Provider Gateway (mock)",
    description=(
        "Stands in for the vendor APIs a lender would call — SentiLink, Socure "
        "and friends are all HTTP services taking identity attributes. All "
        "data here is fabricated for the POC."
    ),
    version="1.0.0",
)


@app.middleware("http")
async def trace_requests(request: Request, call_next):
    """Print each request and, optionally, the response body it returned.

    The body has to be buffered to be logged, so this middleware rebuilds the
    response from the collected chunks rather than streaming it through.
    """
    if not TRACE_ON:
        return await call_next(request)

    started = time.perf_counter()
    response = await call_next(request)
    chunks = [chunk async for chunk in response.body_iterator]
    body = b"".join(chunks)
    elapsed_ms = (time.perf_counter() - started) * 1000

    print(
        f"  → {request.method} {request.url.path} "
        f"{response.status_code} · {elapsed_ms:.0f}ms · {len(body)}B",
        file=sys.stderr,
        flush=True,
    )
    if TRACE_BODY and body:
        try:
            rendered = json.dumps(json.loads(body), indent=2)
        except (json.JSONDecodeError, UnicodeDecodeError):
            rendered = repr(body[:2000])
        print(
            "\n".join(f"      {line}" for line in rendered.splitlines()),
            file=sys.stderr,
            flush=True,
        )

    return Response(
        content=body,
        status_code=response.status_code,
        headers=dict(response.headers),
        media_type=response.media_type,
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
