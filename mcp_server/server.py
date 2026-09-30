"""The MCP tool surface.

Run standalone over stdio (which is how the agent launches it):

    python -m mcp_server

Or over HTTP for other clients:

    python -m mcp_server --transport streamable-http

It needs the provider gateway reachable at PROVIDER_API_URL (default
http://127.0.0.1:8000).

Note what is deliberately NOT here: no submit_case_memo, and no approve /
reject / escalate. Those are not lookups, and exposing the memo write over a
shared tool surface would let any MCP client write to the audit log. The memo
stays inside the agent process, next to the guardrail it depends on.
"""

from __future__ import annotations

import logging
import os

# anthropic 1.x is built on httpx2, so that is what is already installed.
import httpx2 as httpx
from mcp.server.mcpserver import MCPServer

from provider_api.lookups import LOOKUP_DESCRIPTIONS

logging.getLogger("httpx2").setLevel(logging.WARNING)

PROVIDER_API_URL = os.environ.get("PROVIDER_API_URL", "http://127.0.0.1:8000").rstrip("/")
TIMEOUT = float(os.environ.get("PROVIDER_API_TIMEOUT", "20"))

server = MCPServer(
    name="synthetic-identity-lookups",
    instructions=(
        "Read-only identity and credit lookups for a flagged synthetic-identity "
        "case. Every tool takes the applicant_id of the case under "
        "investigation. All data is fabricated for a POC."
    ),
)


def _get(path: str) -> dict:
    url = f"{PROVIDER_API_URL}{path}"
    try:
        response = httpx.get(url, timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        return {"error": f"Provider gateway unreachable at {url}: {exc}"}
    if response.status_code == 404:
        return {"error": response.json().get("detail", "not found")}
    if response.status_code >= 400:
        return {"error": f"Provider gateway returned {response.status_code}: {response.text[:200]}"}
    return response.json()


@server.tool(description=LOOKUP_DESCRIPTIONS["check_ssn_verification"])
def check_ssn_verification(applicant_id: int) -> dict:
    return _get(f"/v1/applicants/{applicant_id}/ssn-verification")


@server.tool(description=LOOKUP_DESCRIPTIONS["check_credit_trajectory"])
def check_credit_trajectory(applicant_id: int) -> dict:
    return _get(f"/v1/applicants/{applicant_id}/credit-trajectory")


@server.tool(description=LOOKUP_DESCRIPTIONS["check_authorized_user_history"])
def check_authorized_user_history(applicant_id: int) -> dict:
    return _get(f"/v1/applicants/{applicant_id}/authorized-user-history")


@server.tool(description=LOOKUP_DESCRIPTIONS["check_shared_identifiers"])
def check_shared_identifiers(applicant_id: int) -> dict:
    return _get(f"/v1/applicants/{applicant_id}/shared-identifiers")
