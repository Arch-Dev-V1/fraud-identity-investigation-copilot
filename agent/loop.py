"""The tool-use loop.

A manual loop rather than the SDK's beta tool runner, for three reasons: the
Streamlit UI needs an event per step to drive ``st.status``; ``web_search`` can
end a turn with ``pause_turn``, which the Python runner does not auto-resume;
and ``submit_case_memo`` has to terminate the loop rather than feed a result
back.

The loop is a generator. It yields events as they happen and never touches
Streamlit, so it can also be driven from a script or a test.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Iterator

import logging

import anthropic

from . import db, demo, tools
from .mcp_bridge import McpUnavailable

log = logging.getLogger(__name__)

MODEL = "claude-opus-5"
MAX_TOKENS = 16000
# Enough turns for every lookup, a couple of searches and a self-check.
MAX_TURNS = 20
# How many times we nudge a model that stops without submitting a memo.
MAX_NUDGES = 2

# Server-side refusal fallbacks: if a safety classifier declines the request,
# the API reroutes rather than handing back an empty turn. Drop the `betas` and
# `fallbacks` arguments below to turn this off.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

# Prompt caching. Every turn resends the whole conversation, so without this the
# system prompt and tool schemas are re-billed at full input rate on each call —
# measured at over half the input of a single investigation, and two thirds of a
# session once the analyst asks follow-ups.
#
# Two breakpoints, which is the shape that holds up for an agent loop:
#   - an explicit one on the system prompt. Render order is tools -> system ->
#     messages, so a breakpoint on the last system block caches the whole stable
#     prefix: tool schemas included.
#   - top-level automatic caching, which handles the growing message tail.
#
# TTL: the default 5 minutes covers an investigation, whose turns land seconds
# apart. Chat follow-ups arrive at human speed and can miss it. "1h" writes at
# 2x instead of 1.25x, so it only pays if it prevents enough misses — switch it
# only on measured gaps between requests, not on a hunch.
CACHE_TTL = "5m"


def _cached_system() -> list[dict[str, Any]]:
    """The system prompt as a cache breakpoint over the stable prefix."""
    cache_control: dict[str, Any] = {"type": "ephemeral"}
    if CACHE_TTL != "5m":
        cache_control["ttl"] = CACHE_TTL
    return [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": cache_control}]

SYSTEM_PROMPT = """\
You are an investigator on a financial-crime team. A scoring provider has \
flagged an application as a possible synthetic identity — an identity that was \
fabricated rather than stolen, typically by pairing a real or unissued SSN with \
invented biographical details and then maturing it with credit until it can \
borrow at scale.

Your job is to reconstruct how this identity was built and hand a human analyst \
a memo they can act on. You are advisory. You do not approve, reject, escalate \
or close anything, and you have no tool that could — the analyst decides.

How to work:

- Start from what is actually suspicious about THIS case. The reason codes tell \
you where the provider's suspicion came from; they are a starting point, not a \
checklist to work through in order. A case flagged for first-party abuse needs a \
different investigation from one flagged for a shared device.
- After each tool result, decide whether you have enough or need more. Do not \
call tools you have no reason to call, and do not stop while an obvious \
question is unanswered.
- Use web_search only for general fraud-pattern context that genuinely changes \
your reading of the evidence — what a mail-drop address type looks like, how a \
known ring operates, whether a pattern is a recognised typology. Never search \
for the applicant. The identity is fabricated demo data; searching for it \
returns nothing and wastes a turn.
- The lookup tools only answer for the applicant under investigation. Other \
applicants surfaced by check_shared_identifiers are context you can reason \
about, not files you can open.

Two things the memo must get right:

1. The counter-narrative is not a disclaimer. Argue the case that this is a real \
person and the flag is wrong, as well as it can be argued, signal by signal. \
An SSN issued after the claimed birth date fits a fabricated identity — it also \
fits someone who immigrated as an adult, or was never enumerated at birth. An \
authorized-user tradeline is how synthetics are matured — it is also how a \
parent helps a teenager build credit. Say what evidence would settle each \
question. If the counter-narrative is genuinely weak, say why it is weak rather \
than leaving it thin.
2. Give a confidence level, never a verdict. "High confidence this identity was \
fabricated" is a finding. "This is fraud, reject it" is a decision that is not \
yours to make.

Before you submit, check your own work: is every claim in the evidence list tied \
to something a tool actually returned, and is the counter-narrative substantive? \
If not, go back and investigate further.

When you are done, call submit_case_memo exactly once.
"""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# The four token classes bill at four different rates, so they are kept apart
# rather than summed. web_search is a per-use fee on top of tokens.
_USAGE_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)


def _usage_snapshot(response: Any) -> dict[str, int] | None:
    """Pull the usage meters off one response.

    Returns None in demo mode, where there is no real usage to report — a zero
    would read as "this cost nothing to run", which is true, but a fabricated
    token count would not be.
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    snapshot = {field: int(getattr(usage, field, 0) or 0) for field in _USAGE_FIELDS}
    details = getattr(usage, "output_tokens_details", None)
    if details is not None:
        snapshot["thinking_tokens"] = int(getattr(details, "thinking_tokens", 0) or 0)
    server = getattr(usage, "server_tool_use", None)
    if server is not None:
        snapshot["web_search_requests"] = int(getattr(server, "web_search_requests", 0) or 0)
    return snapshot


def _total_usage(snapshots: list[dict[str, int]]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for snapshot in snapshots:
        for key, value in snapshot.items():
            totals[key] = totals.get(key, 0) + value
    return totals


def build_opening_prompt(case: dict) -> str:
    """What the agent is told before it picks its first tool."""
    return f"""\
A new application has been flagged for review.

Applicant id: {case['id']}   (pass this id to the lookup tools)
Name:            {case['name']}
Claimed DOB:     {case['claimed_dob']}
SSN:             {case['ssn']}
Claimed address: {case['claimed_address']}
Claimed phone:   {case['claimed_phone']}
Claimed email:   {case['claimed_email']}

Provider score (0-999 scale, higher is riskier):
  Composite abuse score:  {case['abuse_score']}   (risk tier: {case['risk_tier']})
  First-party synthetic:  {case['first_party_synthetic_score']}
  Third-party synthetic:  {case['third_party_synthetic_score']}
  Reason codes:           {case['reason_codes']}

Investigate this case and submit a memo."""


def memo_to_markdown(memo: dict, case: dict) -> str:
    """Render the structured memo for the analyst and for audit_log."""
    lines = [
        f"## Case memo — {case['name']} (applicant {case['id']})",
        "",
        f"**Confidence this identity is synthetic: {memo['confidence_level'].upper()}**  ",
        "_Advisory only — no disposition has been made. The analyst decides._",
        "",
        memo["summary"],
        "",
        "### Maturation timeline",
        "",
    ]
    for step in memo.get("timeline", []):
        lines.append(f"- **{step['date']}** — {step['event']}  ")
        lines.append(f"  _{step['significance']}_")
    lines += ["", "### Evidence", ""]
    for item in memo.get("evidence", []):
        lines.append(
            f"- **{item['finding']}** ({item['strength']}) — {item['detail']}  "
        )
        lines.append(f"  _source: `{item['source_tool']}`_")
    lines += [
        "",
        "### Counter-narrative — the case that this is a real person",
        "",
        memo["counter_narrative"],
    ]
    return "\n".join(lines)


_NO_CREDENTIALS = (
    "No Anthropic credentials found. Set ANTHROPIC_API_KEY in your environment, "
    "put it in a .env file in the project root, or run `ant auth login` — then "
    "start the investigation again."
)

# An organisation-level key is valid but unusable without naming a workspace.
_NEEDS_WORKSPACE = (
    "This API key is not scoped to a workspace, so the request has to name one. "
    "Two fixes, either is fine: create a key inside a workspace in the Anthropic "
    "Console and use that instead, or set ANTHROPIC_WORKSPACE_ID (in .env or the "
    "environment) to the workspace id — it is the `wrkspc_...` value in the "
    "Console URL when you have that workspace open."
)

# A rejected key is a different problem from a missing one, and conflating them
# sends people to edit a file that is already correct. This message is for the
# case where a key WAS found and sent, and the API refused it.
_KEY_REJECTED = (
    "The API rejected the credentials. A key was found and sent, so the file or "
    "environment variable holding it is working — the key itself is the problem. "
    "It has most likely been revoked or rotated, or belongs to a workspace that "
    "no longer exists. Check it in the Anthropic Console and paste the current "
    "one. Run `python -m agent.check_credentials` to confirm before trying again."
)


def client_headers() -> dict[str, str]:
    """Extra headers the client needs, if any.

    An API key created at organisation level rather than inside a workspace is
    accepted by the API but cannot be used on its own: the request has to name
    the workspace. Setting ANTHROPIC_WORKSPACE_ID makes such a key usable. A
    workspace-scoped key needs none of this and ignores it.
    """
    workspace = os.environ.get("ANTHROPIC_WORKSPACE_ID", "").strip()
    return {"anthropic-workspace-id": workspace} if workspace else {}


def _client() -> anthropic.Anthropic:
    # Deliberately no credential preflight here: the SDK also resolves an
    # `ant auth login` profile and federated env vars, so an unset
    # ANTHROPIC_API_KEY does not mean there is no credential. A genuinely
    # missing one surfaces as an error event from the loop below.
    headers = client_headers()
    return anthropic.Anthropic(default_headers=headers) if headers else anthropic.Anthropic()


def run_investigation(
    applicant_id: int,
    client: anthropic.Anthropic | None = None,
    db_path=None,
    demo_mode: bool | None = None,
    transport: str | None = None,
    user_message: str | None = None,
    history: list[dict[str, Any]] | None = None,
    require_memo: bool = True,
) -> Iterator[dict[str, Any]]:
    """Run one turn against a case, yielding events as they happen.

    Event types: ``start``, ``thinking``, ``narration``, ``tool_call``,
    ``tool_result``, ``search``, ``reply``, ``memo``, ``turn_complete``,
    ``error``, ``done``.

    ``user_message`` is the analyst's message for this turn. Left out, the
    agent is handed the generated case brief instead, which is what the
    "run investigation" path sends.

    ``history`` is the prior conversation, as returned by the last
    ``turn_complete`` event, so the agent can be talked to across turns rather
    than only once per case.

    ``require_memo`` distinguishes the two things an analyst can ask for. True
    (running an investigation) means a turn that ends without calling
    submit_case_memo gets nudged back. False (an ordinary chat message) means a
    plain text answer is a complete, correct response — asking "what does ECOA
    3 mean" should not force a memo.

    ``demo_mode`` replaces Claude with a canned analyzer so the whole flow runs
    with no API key and no cost; everything else — tools, database, guardrails —
    is the real thing. Defaults to the DEMO_MODE environment variable.

    ``transport`` is ``mcp`` (the real path: MCP server over stdio, calling the
    provider gateway over HTTP) or ``direct`` (in-process lookups). Defaults to
    TOOL_TRANSPORT, and falls back to direct with a note if the gateway is down.
    """
    case = db.get_case(applicant_id, db_path)
    if demo_mode is None:
        demo_mode = demo.is_demo_mode()
    if client is None:
        client = demo.DemoClient(case, investigate=require_memo) if demo_mode else _client()

    active_transport, transport_note = tools.resolve_transport(transport)
    bridge = None
    if active_transport == tools.TRANSPORT_MCP:
        try:
            bridge = tools.open_bridge(active_transport)
            tool_list = tools.build_tool_list(active_transport, bridge)
        except (McpUnavailable, Exception) as exc:
            # The gateway answered but the MCP server itself would not start.
            # Say so and carry on in-process rather than failing the case.
            if bridge is not None:
                bridge.close()
                bridge = None
            active_transport = tools.TRANSPORT_DIRECT
            transport_note = f"Could not start the MCP server ({exc}); using in-process lookups."
            tool_list = tools.build_tool_list(active_transport)
    else:
        tool_list = tools.build_tool_list(active_transport)

    yield {
        "type": "start",
        "case": case,
        "demo_mode": demo_mode,
        "transport": active_transport,
        "transport_note": transport_note,
    }
    try:
        yield from _investigate(
            applicant_id, case, client, db_path, demo_mode, active_transport,
            bridge, tool_list, user_message, history, require_memo,
        )
    finally:
        if bridge is not None:
            bridge.close()


def _investigate(
    applicant_id: int,
    case: dict,
    client: Any,
    db_path,
    demo_mode: bool,
    active_transport: str,
    bridge: Any,
    tool_list: list[dict],
    user_message: str | None = None,
    history: list[dict[str, Any]] | None = None,
    require_memo: bool = True,
) -> Iterator[dict[str, Any]]:
    """The loop proper. Split out so run_investigation can guarantee the MCP
    bridge is closed even if the caller abandons the generator."""

    messages: list[dict[str, Any]] = list(history or [])
    messages.append({
        "role": "user",
        "content": user_message or build_opening_prompt(case),
    })
    trail: list[dict[str, Any]] = []  # goes to audit_log.tool_calls_made
    usage_log: list[dict[str, int]] = []   # one entry per model call
    nudges = 0
    # Text the agent produced this turn, so a chat reply can be handed back as
    # one message rather than as loose narration events.
    said: list[str] = []

    for _ in range(MAX_TURNS):
        try:
            response = client.beta.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=_cached_system(),
                cache_control={"type": "ephemeral"},
                thinking={"type": "adaptive", "display": "summarized"},
                tools=tool_list,
                messages=messages,
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
        except anthropic.AuthenticationError:
            yield {"type": "error", "message": _KEY_REJECTED}
            return
        except anthropic.BadRequestError as exc:
            if "workspace" in str(exc).lower():
                yield {"type": "error", "message": _NEEDS_WORKSPACE}
            else:
                yield {"type": "error", "message": f"Bad request: {exc}"}
            return
        except anthropic.PermissionDeniedError as exc:
            yield {
                "type": "error",
                "message": ("The credentials are valid but lack access to this "
                            f"model or workspace: {exc}"),
            }
            return
        except anthropic.APIStatusError as exc:
            yield {"type": "error", "message": f"API error {exc.status_code}: {exc}"}
            return
        except anthropic.APIConnectionError as exc:
            yield {"type": "error", "message": f"Could not reach the API: {exc}"}
            return
        except TypeError as exc:
            # The SDK raises a bare TypeError at request time — not an
            # AuthenticationError — when it cannot resolve any credential.
            message = _NO_CREDENTIALS if "authentication method" in str(exc) else f"{exc}"
            yield {"type": "error", "message": message}
            return
        except Exception as exc:  # backstop: the caller always gets an event
            yield {"type": "error", "message": f"{type(exc).__name__}: {exc}"}
            return

        snapshot = _usage_snapshot(response)
        if snapshot is not None:
            usage_log.append(snapshot)
            log.info("turn usage applicant=%s %s", applicant_id, snapshot)
            # The served model, from the response rather than from config: a
            # silent substitution (a provider fallback, a capacity reroute)
            # would otherwise invalidate any comparison built on these runs.
            yield {"type": "usage", "usage": snapshot,
                   "model": getattr(response, "model", None),
                   "totals": _total_usage(usage_log)}

        if response.stop_reason == "refusal":
            detail = getattr(response, "stop_details", None)
            yield {
                "type": "error",
                "message": f"The model declined this request ({detail}).",
            }
            return

        # Surface everything in the turn before acting on it.
        for block in response.content:
            if block.type == "thinking" and getattr(block, "thinking", ""):
                yield {"type": "thinking", "text": block.thinking}
            elif block.type == "text" and block.text.strip():
                said.append(block.text)
                yield {"type": "narration", "text": block.text}
            elif block.type == "server_tool_use" and block.name == "web_search":
                query = (block.input or {}).get("query", "")
                trail.append({
                    "tool": "web_search",
                    "input": {"query": query},
                    "output": "(results returned by Anthropic's web search)",
                    "timestamp": _utcnow(),
                })
                yield {"type": "search", "query": query}
            elif block.type == "web_search_tool_result":
                content = block.content
                # An error comes back as an object, a success as a list.
                if isinstance(content, list):
                    yield {
                        "type": "tool_result",
                        "tool": "web_search",
                        "output": f"{len(content)} result(s)",
                        "is_error": False,
                    }
                else:
                    code = getattr(content, "error_code", "unknown_error")
                    yield {
                        "type": "tool_result",
                        "tool": "web_search",
                        "output": f"search failed: {code}",
                        "is_error": True,
                    }

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "pause_turn":
            # A long server-tool turn was paused; resend to let it continue.
            continue

        tool_uses = [b for b in response.content if b.type == "tool_use"]

        if not tool_uses:
            if not require_memo:
                # An ordinary chat turn: a text answer is the whole response.
                yield {
                    "type": "reply",
                    "text": "\n\n".join(said).strip() or "(no reply)",
                    "usage_totals": _total_usage(usage_log),
                }
                yield {"type": "turn_complete", "messages": messages}
                yield {"type": "done"}
                return
            if nudges >= MAX_NUDGES:
                # Give back whatever was actually said rather than losing it.
                if said:
                    yield {"type": "reply", "text": "\n\n".join(said).strip()}
                    yield {"type": "turn_complete", "messages": messages}
                yield {
                    "type": "error",
                    "message": "The agent finished without submitting a case memo.",
                }
                return
            nudges += 1
            messages.append({
                "role": "user",
                "content": (
                    "You have not submitted a case memo yet. Either call another "
                    "lookup tool if evidence is still missing, or call "
                    "submit_case_memo now."
                ),
            })
            continue

        tool_results = []
        for tool_use in tool_uses:
            if tool_use.name in tools.TERMINAL_TOOLS:
                memo = dict(tool_use.input)
                totals = _total_usage(usage_log)
                trail.append({
                    "tool": tool_use.name,
                    "input": {"confidence_level": memo.get("confidence_level")},
                    "output": "memo written to audit_log",
                    "demo_mode": demo_mode,
                    "model_calls": len(usage_log),
                    "token_usage": totals or "not recorded (demo mode)",
                    "timestamp": _utcnow(),
                })
                markdown = memo_to_markdown(memo, case)
                if demo_mode:
                    markdown = f"{demo.DEMO_BANNER}\n\n{markdown}"
                audit_log_id = db.write_memo(
                    applicant_id=applicant_id,
                    tool_calls_made=json.dumps(trail, indent=2),
                    case_memo=markdown,
                    confidence_level=memo["confidence_level"],
                    db_path=db_path,
                )
                messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": f"Memo saved as audit_log row {audit_log_id}. "
                                   "A human analyst decides the disposition.",
                    }],
                })
                yield {
                    "type": "memo",
                    "demo_mode": demo_mode,
                    "usage_totals": totals,
                    "memo": memo,
                    "markdown": markdown,
                    "audit_log_id": audit_log_id,
                    "trail": trail,
                }
                yield {"type": "turn_complete", "messages": messages}
                yield {"type": "done"}
                return

            yield {"type": "tool_call", "tool": tool_use.name, "input": tool_use.input}
            output, is_error = tools.execute_tool(
                tool_use.name,
                dict(tool_use.input),
                applicant_id,
                db_path,
                transport=active_transport,
                bridge=bridge,
            )
            trail.append({
                "tool": tool_use.name,
                "input": dict(tool_use.input),
                "output": json.loads(output),
                "timestamp": _utcnow(),
            })
            yield {
                "type": "tool_result",
                "tool": tool_use.name,
                "output": output,
                "is_error": is_error,
            }
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": output,
                **({"is_error": True} if is_error else {}),
            })

        messages.append({"role": "user", "content": tool_results})

    yield {
        "type": "error",
        "message": f"Stopped after {MAX_TURNS} turns without a case memo.",
    }
