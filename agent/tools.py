"""Tool definitions, transports, and the scope guard.

The four lookups reach the data one of two ways:

``mcp``    the agent talks to the MCP server (launched over stdio), which calls
           the provider gateway over HTTP, which reads SQLite. This is the real
           path and the one the architecture is built around.
``direct`` the agent calls provider_api.lookups in-process. Same functions, so
           identical response shapes — this exists so demo mode and the tests
           run with nothing else started.

``submit_case_memo`` is deliberately NOT on the MCP surface. It is not a
lookup, and exposing the memo write over a shared tool surface would let any
MCP client write to the audit log. It stays in-process, next to the guardrail
it depends on.

Whichever transport is in use, a lookup only ever answers for the applicant
under investigation. That check lives here, on the agent side, because only the
agent knows which case is open — the MCP server is a generic surface and must
not be trusted to enforce it.
"""

from __future__ import annotations

import json
import os
from typing import Any

from . import db
from .mcp_bridge import McpBridge, McpUnavailable, anthropic_tool_definitions, stdio_target

try:  # httpx2 ships with anthropic 1.x
    import httpx2 as httpx
except ModuleNotFoundError:  # pragma: no cover
    httpx = None

from provider_api.lookups import LOOKUPS, LOOKUP_DESCRIPTIONS, LookupNotFound

PROVIDER_API_URL = os.environ.get("PROVIDER_API_URL", "http://127.0.0.1:8000").rstrip("/")

TRANSPORT_MCP = "mcp"
TRANSPORT_DIRECT = "direct"


def default_transport() -> str:
    """``TOOL_TRANSPORT`` picks the transport; MCP is the default."""
    value = os.environ.get("TOOL_TRANSPORT", TRANSPORT_MCP).strip().lower()
    return value if value in (TRANSPORT_MCP, TRANSPORT_DIRECT) else TRANSPORT_MCP


def gateway_reachable(timeout: float = 2.0) -> bool:
    if httpx is None:
        return False
    try:
        return httpx.get(f"{PROVIDER_API_URL}/health", timeout=timeout).status_code == 200
    except Exception:
        return False


def resolve_transport(preferred: str | None = None) -> tuple[str, str | None]:
    """Decide which transport to actually use.

    Returns ``(transport, note)``. If MCP is wanted but the provider gateway is
    not running, this falls back to ``direct`` and says so in the note — the
    caller is expected to surface that rather than swallow it, so nobody
    mistakes a fallback for the real path.
    """
    preferred = (preferred or default_transport()).lower()
    if preferred != TRANSPORT_MCP:
        return TRANSPORT_DIRECT, None
    if gateway_reachable():
        return TRANSPORT_MCP, None
    return TRANSPORT_DIRECT, (
        f"Provider gateway is not reachable at {PROVIDER_API_URL}, so the MCP "
        "path is unavailable; falling back to in-process lookups. Start it with "
        "`uvicorn provider_api.main:app --port 8000` for the full stack."
    )


# --- tool schemas ----------------------------------------------------------

_APPLICANT_ID_SCHEMA = {
    "type": "object",
    "properties": {
        "applicant_id": {
            "type": "integer",
            "description": "The id of the applicant under investigation.",
        }
    },
    "required": ["applicant_id"],
    "additionalProperties": False,
}

SUBMIT_CASE_MEMO = {
    "name": "submit_case_memo",
    "description": (
        "Submit the finished case memo and end the investigation. This is "
        "advisory only: it records your analysis for a human analyst and does "
        "not approve, reject, escalate or otherwise dispose of the case. Call "
        "it exactly once, after the evidence is strong enough to stand on its "
        "own and the counter-narrative is genuinely substantive."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "timeline": {
                "type": "array",
                "description": (
                    "The identity's maturation history in date order — how this "
                    "identity was built up over time."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "date": {
                            "type": "string",
                            "description": "YYYY-MM-DD, or YYYY-MM / YYYY if that is all the evidence supports.",
                        },
                        "event": {"type": "string", "description": "What happened, in one sentence."},
                        "significance": {
                            "type": "string",
                            "description": "Why this step matters to the assessment.",
                        },
                    },
                    "required": ["date", "event", "significance"],
                    "additionalProperties": False,
                },
            },
            "evidence": {
                "type": "array",
                "description": "Each finding, tied to the tool that produced it.",
                "items": {
                    "type": "object",
                    "properties": {
                        "finding": {"type": "string"},
                        "source_tool": {"type": "string", "description": "The tool this finding came from."},
                        "detail": {
                            "type": "string",
                            "description": "The specific values that support it — dates, amounts, identifiers.",
                        },
                        "strength": {"type": "string", "enum": ["weak", "moderate", "strong"]},
                    },
                    "required": ["finding", "source_tool", "detail", "strength"],
                    "additionalProperties": False,
                },
            },
            "counter_narrative": {
                "type": "string",
                "description": (
                    "The substantive case that this applicant is a real person "
                    "and the flag is wrong: the innocent explanation for each "
                    "major signal, and what evidence would settle it. Not a "
                    "disclaimer — argue it properly."
                ),
            },
            "confidence_level": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": (
                    "Confidence that this is a synthetic identity. Never a yes/no verdict."
                ),
            },
            "summary": {
                "type": "string",
                "description": "Two or three sentences an analyst can read first.",
            },
        },
        "required": ["timeline", "evidence", "counter_narrative", "confidence_level", "summary"],
        "additionalProperties": False,
    },
}

# web_search is Anthropic-hosted; there is no implementation because it does
# not run locally.
WEB_SEARCH = {"type": "web_search_20260209", "name": "web_search", "max_uses": 4}

LOOKUP_NAMES = tuple(LOOKUPS)
TERMINAL_TOOLS = {"submit_case_memo"}
SERVER_TOOLS = {"web_search"}


def direct_lookup_definitions() -> list[dict]:
    """Claude tool definitions for the in-process transport, described by the
    same strings the MCP server publishes."""
    return [
        {
            "name": name,
            "description": LOOKUP_DESCRIPTIONS[name],
            "strict": True,
            "input_schema": _APPLICANT_ID_SCHEMA,
        }
        for name in LOOKUP_NAMES
    ]


def build_tool_list(transport: str, bridge: McpBridge | None = None) -> list[dict]:
    """The tools handed to Claude: the lookups for this transport, plus the two
    that never leave the agent process."""
    if transport == TRANSPORT_MCP:
        if bridge is None:
            raise ValueError("The MCP transport needs a started McpBridge.")
        lookups = anthropic_tool_definitions(bridge.list_tools())
    else:
        lookups = direct_lookup_definitions()
    return [*lookups, WEB_SEARCH, SUBMIT_CASE_MEMO]


# --- dispatch --------------------------------------------------------------


def _out_of_scope(requested: Any, case_applicant_id: int) -> str:
    return json.dumps({
        "error": (
            f"applicant_id {requested!r} is out of scope. This investigation "
            f"covers applicant {case_applicant_id} only. Other applicants "
            "surfaced by check_shared_identifiers are context, not cases you "
            "can look up."
        )
    })


def execute_tool(
    name: str,
    tool_input: dict,
    case_applicant_id: int,
    db_path=None,
    transport: str = TRANSPORT_DIRECT,
    bridge: McpBridge | None = None,
) -> tuple[str, bool]:
    """Run one lookup. Returns ``(result_json, is_error)``."""
    if name not in LOOKUPS:
        return json.dumps({"error": f"Unknown tool: {name}"}), True

    # The scope guard runs before any transport, so it holds whether the lookup
    # is answered in-process or over MCP.
    requested = tool_input.get("applicant_id")
    if requested != case_applicant_id:
        return _out_of_scope(requested, case_applicant_id), True

    if transport == TRANSPORT_MCP:
        if bridge is None:
            return json.dumps({"error": "MCP transport selected but no bridge is started."}), True
        try:
            return bridge.call_tool(name, {"applicant_id": case_applicant_id})
        except (McpUnavailable, TimeoutError) as exc:
            return json.dumps({"error": f"MCP call failed: {exc}"}), True
        except Exception as exc:
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"}), True

    conn = db.connect(db_path)
    try:
        return json.dumps(LOOKUPS[name](conn, case_applicant_id), default=str), False
    except LookupNotFound as exc:
        return json.dumps({"error": str(exc)}), True
    except Exception as exc:
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"}), True
    finally:
        conn.close()


def open_bridge(transport: str) -> McpBridge | None:
    """Start the MCP bridge for an investigation, or None for direct mode."""
    if transport != TRANSPORT_MCP:
        return None
    return McpBridge(stdio_target()).start()
