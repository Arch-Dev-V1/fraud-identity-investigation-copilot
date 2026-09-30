"""Synthetic Identity Investigation Copilot — analyst UI.

Two panels. Left: the conversation with the agent — message history, the live
investigation feed, and the composer with Run investigation below it. Right: the
flagged-case feed, the snapshot of whichever case is selected, and the decision
buttons.

This file only talks to the `agent` module. It has no database access and no
model access of its own.
"""

from __future__ import annotations

import inspect
import json
import os

import streamlit as st

import agent

st.set_page_config(
    page_title="Synthetic Identity Investigation Copilot",
    page_icon="🕵️",
    layout="wide",
)

AGENT_AVATAR = "🕵️"
TIER_COLOR = {"high": "🔴", "medium": "🟠", "low": "🟡"}
DECISION_LABEL = {
    "approved": "Approved",
    "rejected": "Rejected",
    "escalated": "Escalated for more evidence",
}
TOOL_LABEL = {
    "check_ssn_verification": "Verifying SSN against SSA and credit-header history",
    "check_credit_trajectory": "Pulling credit trajectory and payment history",
    "check_authorized_user_history": "Checking authorized-user history",
    "check_shared_identifiers": "Looking for identifiers shared with other flagged applications",
    "web_search": "Searching for fraud-pattern context",
}


# Arguments this file passes to agent.run_investigation. Checked at startup
# because Streamlit re-runs app.py on save but keeps already-imported local
# modules cached in sys.modules: edit anything under agent/ while the server is
# running and you get a new app.py calling an old agent, which surfaces as a
# bare TypeError about an unexpected keyword argument. Naming the real problem
# is worth the few lines.
_TURN_ARGUMENTS = ("user_message", "history", "require_memo")


def _require_current_agent_module() -> None:
    parameters = set(inspect.signature(agent.run_investigation).parameters)
    missing = [name for name in _TURN_ARGUMENTS if name not in parameters]
    if not missing:
        return
    st.error(
        "**The loaded `agent` module is out of date — restart the app.**\n\n"
        f"`agent.run_investigation` is missing: `{'`, `'.join(missing)}`.\n\n"
        "Streamlit re-runs `app.py` when it changes but does not reload local "
        "modules it has already imported, so edits under `agent/` only take "
        "effect on a restart. Stop the server with Ctrl+C and start it again "
        "(`./run.sh`).",
        icon="♻️",
    )
    st.stop()


# --- state ------------------------------------------------------------------

def _has_credentials() -> bool:
    return bool(
        os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
    )


def _state():
    ss = st.session_state
    ss.setdefault("selected_case_id", None)
    ss.setdefault("transcripts", {})     # applicant_id -> [display messages]
    ss.setdefault("histories", {})       # applicant_id -> model message history
    ss.setdefault("runs", {})            # applicant_id -> memo record
    ss.setdefault("pending", None)       # {applicant_id, message, require_memo}
    # The composer's text lives in composer_draft, not in the widget key:
    # Streamlit forbids writing a widget's key after the widget has been
    # instantiated, and the send buttons render below it. Rotating the key is
    # what lets us clear or refill the box.
    ss.setdefault("composer_draft", "")
    ss.setdefault("composer_nonce", 0)
    ss.setdefault("autofilled_text", "")
    # Default to demo mode when there is nothing to bill against, so the app is
    # never a dead end — but never override an explicit DEMO_MODE=1.
    ss.setdefault("demo_mode", agent.is_demo_mode() or not _has_credentials())
    return ss


def _composer_key() -> str:
    return f"composer_{_state().composer_nonce}"


def _composer_value() -> str:
    """Whatever is in the box right now — the live widget if it has rendered,
    otherwise the draft we are about to render with."""
    return st.session_state.get(_composer_key(), _state().composer_draft) or ""


def _set_composer(text: str) -> None:
    state = _state()
    stale = _composer_key()
    state.composer_draft = text
    state.composer_nonce += 1   # a fresh key, so `value` takes effect again
    # Drop the retired widget's entry so keys do not pile up over a session.
    st.session_state.pop(stale, None)


def _fill_brief(case: dict) -> None:
    """Drop this case's brief into the composer and remember that we did, so a
    later refill can tell our text apart from the analyst's."""
    brief = agent.build_opening_prompt(case)
    _set_composer(brief)
    _state().autofilled_text = brief


def _transcript(applicant_id: int) -> list[dict]:
    return _state().transcripts.setdefault(applicant_id, [])


def _run_record(applicant_id: int) -> dict | None:
    """The in-session run if there is one, otherwise the last memo on disk."""
    state = _state()
    if applicant_id in state.runs:
        return state.runs[applicant_id]
    stored = agent.latest_memo(applicant_id)
    if stored:
        return {
            "events": [],
            "markdown": stored["case_memo"],
            "audit_log_id": stored["id"],
            "confidence_level": stored["confidence_level"],
            "trail": json.loads(stored["tool_calls_made"]),
            "from_disk": True,
        }
    return None


def _queue(applicant_id: int, require_memo: bool) -> None:
    """Send whatever is in the composer as this turn's message."""
    message = _composer_value().strip()
    if not message:
        st.toast("Nothing to send — the message is empty.", icon="✍️")
        return
    _state().pending = {
        "applicant_id": applicant_id,
        "message": message,
        "require_memo": require_memo,
    }
    _set_composer("")
    st.rerun()


# --- rendering --------------------------------------------------------------

def render_step_replay(events: list[dict]) -> None:
    """Replay the feed inside an expander. Flat markdown only — Streamlit
    expanders cannot nest, and render_event uses them."""
    for event in events:
        kind = event["type"]
        if kind == "tool_call":
            st.markdown(f"**{TOOL_LABEL.get(event['tool'], event['tool'])}** · `{event['tool']}`")
        elif kind == "search":
            st.markdown(f"**Web search** · _{event['query']}_")
        elif kind == "tool_result":
            mark = "⚠️ " if event.get("is_error") else ""
            st.caption(f"↳ {mark}{event['tool']} returned {len(event['output'])} chars")
        elif kind == "narration":
            st.markdown(f"> {event['text']}")
        elif kind == "thinking":
            st.caption(event["text"])


def render_event(event: dict, container) -> None:
    kind = event["type"]
    if kind == "thinking":
        with container.expander("Reasoning", expanded=False):
            st.markdown(event["text"])
    elif kind == "narration":
        container.markdown(event["text"])
    elif kind == "tool_call":
        label = TOOL_LABEL.get(event["tool"], event["tool"])
        container.markdown(f"**{label}** · `{event['tool']}`")
    elif kind == "search":
        container.markdown(f"**Web search** · _{event['query']}_")
    elif kind == "tool_result":
        if event.get("is_error"):
            container.markdown(f"↳ ⚠️ {event['output']}")
        else:
            with container.expander(f"↳ result from `{event['tool']}`", expanded=False):
                try:
                    st.json(json.loads(event["output"]))
                except (json.JSONDecodeError, TypeError):
                    st.write(event["output"])
    elif kind == "error":
        container.error(event["message"])


def render_message(message: dict) -> None:
    """One turn in the transcript."""
    if message["role"] == "user":
        with st.chat_message("user"):
            st.markdown(message["text"])
        return

    with st.chat_message("assistant", avatar=AGENT_AVATAR):
        if message["kind"] == "memo":
            st.markdown(message["markdown"])
            if message.get("events"):
                with st.expander("Investigation steps", expanded=False):
                    render_step_replay(message["events"])
            with st.expander("Tool-call trail (audit_log)", expanded=False):
                st.caption(
                    f"audit_log row {message['audit_log_id']} · "
                    f"{len(message['trail'])} tool call(s) recorded"
                )
                st.json(message["trail"])
        elif message["kind"] == "error":
            st.error(message["text"])
        else:
            st.markdown(message["text"])


def run_turn(applicant_id: int, case: dict, message: str, require_memo: bool) -> None:
    """Drive one turn, streaming each step into st.status, then record it."""
    state = _state()
    transcript = _transcript(applicant_id)
    transcript.append({"role": "user", "kind": "text", "text": message})
    render_message(transcript[-1])

    events: list[dict] = []
    memo_event: dict | None = None
    reply_text: str | None = None
    error_text: str | None = None
    history = state.histories.get(applicant_id)

    label = "Investigating…" if require_memo else "Thinking…"
    with st.status(label, expanded=True) as status:
        try:
            for event in agent.run_investigation(
                applicant_id,
                demo_mode=state.demo_mode,
                user_message=message,
                history=history,
                require_memo=require_memo,
            ):
                events.append(event)
                kind = event["type"]
                if kind == "start":
                    st.caption(
                        f"Tool transport: `{event.get('transport', '?')}`"
                        + ("  ·  MCP server → provider gateway → SQLite"
                           if event.get("transport") == "mcp"
                           else "  ·  in-process lookups")
                    )
                    if event.get("transport_note"):
                        st.warning(event["transport_note"], icon="🔌")
                    if event.get("demo_mode"):
                        st.markdown(
                            ":orange[**Demo mode** — canned analysis from real tool "
                            "results. No model call, no cost.]"
                        )
                elif kind == "memo":
                    memo_event = event
                    st.markdown("**Case memo submitted.**")
                elif kind == "reply":
                    reply_text = event["text"]
                elif kind == "turn_complete":
                    state.histories[applicant_id] = event["messages"]
                elif kind == "error":
                    error_text = event["message"]
                    render_event(event, st)
                else:
                    render_event(event, st)
        except Exception as exc:  # keep the UI alive on an unexpected failure
            status.update(label=f"Failed: {exc}", state="error")
            st.exception(exc)
            transcript.append({"role": "assistant", "kind": "error", "text": str(exc)})
            return

        if error_text:
            status.update(label="Ended without a memo", state="error")
        elif memo_event:
            status.update(label=f"Investigation complete — {case['name']}", state="complete")
        else:
            status.update(label="Done", state="complete")

    if memo_event:
        record = {
            "events": events,
            "markdown": memo_event["markdown"],
            "memo": memo_event["memo"],
            "audit_log_id": memo_event["audit_log_id"],
            "confidence_level": memo_event["memo"]["confidence_level"],
            "trail": memo_event["trail"],
        }
        state.runs[applicant_id] = record
        transcript.append({
            "role": "assistant",
            "kind": "memo",
            "markdown": record["markdown"],
            "audit_log_id": record["audit_log_id"],
            "trail": record["trail"],
            "events": events,
        })
    elif reply_text:
        transcript.append({"role": "assistant", "kind": "text", "text": reply_text})
    elif error_text:
        transcript.append({"role": "assistant", "kind": "error", "text": error_text})


# --- left panel: the conversation ------------------------------------------

def render_chat_panel(case: dict) -> None:
    state = _state()
    applicant_id = case["id"]

    st.subheader("Investigation chat")
    st.caption(
        f"Working on **{case['name']}** (applicant {applicant_id}). Selecting a case "
        "drops its brief into the composer; edit it, add a question, or send it as is."
    )

    for message in _transcript(applicant_id):
        render_message(message)

    pending = state.pending
    if pending and pending["applicant_id"] == applicant_id:
        state.pending = None
        run_turn(applicant_id, case, pending["message"], pending["require_memo"])
        st.rerun()

    if not _transcript(applicant_id):
        st.info(
            "No messages yet for this case. **Run investigation** sends the brief "
            "below and works the case end to end; **Send** just asks a question."
        )

    st.text_area(
        "Message",
        value=state.composer_draft,
        key=_composer_key(),
        height=190,
        placeholder="Ask a question, or send the case brief to start an investigation…",
        label_visibility="collapsed",
    )

    run_col, send_col = st.columns([2, 1])
    if run_col.button(
        "🔍 Run investigation",
        type="primary",
        use_container_width=True,
        help="Send the composer as an investigation request — the agent works the "
             "case and submits a memo.",
    ):
        _queue(applicant_id, require_memo=True)
    if send_col.button(
        "Send",
        use_container_width=True,
        help="Send as an ordinary message and get an answer back.",
    ):
        _queue(applicant_id, require_memo=False)

    left, right = st.columns([1, 1])
    if left.button("Refill brief", use_container_width=True):
        _fill_brief(case)
        st.rerun()
    if right.button("Clear chat", use_container_width=True):
        state.transcripts[applicant_id] = []
        state.histories.pop(applicant_id, None)
        st.rerun()


# --- right panel: cases, snapshot, decision --------------------------------

def render_case_feed(cases: list[dict], selected_id: int) -> None:
    state = _state()
    st.subheader("Flagged cases")
    st.caption("All data is fabricated for this demo.")
    for case in cases:
        marker = TIER_COLOR.get(case["risk_tier"], "")
        decided = (
            f" · {DECISION_LABEL[case['latest_decision']]}"
            if case["latest_decision"] else ""
        )
        is_selected = case["id"] == selected_id
        if st.button(
            f"{marker} **{case['name']}** — {case['abuse_score']}{decided}",
            key=f"case_{case['id']}",
            use_container_width=True,
            type="primary" if is_selected else "secondary",
        ):
            state.selected_case_id = case["id"]
            # Selecting a case drops its brief into the composer. The feed rows
            # are summaries, so the full record has to be fetched to build one.
            current = _composer_value().strip()
            if not current or current == state.autofilled_text.strip():
                _fill_brief(agent.get_case(case["id"]))
            else:
                st.toast(
                    "Kept your draft — use Refill brief to load this case's brief.",
                    icon="✍️",
                )
            st.rerun()


def render_snapshot(case: dict) -> None:
    st.subheader(case["name"])
    tier = case["risk_tier"]
    st.metric(
        "Composite abuse score",
        case["abuse_score"],
        delta=f"{TIER_COLOR.get(tier, '')} {tier} risk",
        delta_color="off",
    )
    left, right = st.columns(2)
    left.metric("First-party", case["first_party_synthetic_score"])
    right.metric("Third-party", case["third_party_synthetic_score"])
    with st.expander("Applicant details", expanded=False):
        st.markdown(
            f"**DOB** {case['claimed_dob']}  \n"
            f"**SSN** {case['ssn']}  \n"
            f"**Phone** {case['claimed_phone']}  \n"
            f"**Address** {case['claimed_address']}  \n"
            f"**Email** {case['claimed_email']}"
        )
    st.caption("Reason codes")
    st.code("\n".join(case["reason_codes"].split(",")), language=None)


def render_decision_panel(applicant_id: int) -> None:
    st.subheader("Analyst decision")
    record = _run_record(applicant_id)

    if record is None:
        st.caption("Available once a case memo has been submitted.")
        return

    stored = agent.get_memo(record["audit_log_id"])
    if stored and stored["analyst_decision"]:
        st.success(
            f"**{DECISION_LABEL[stored['analyst_decision']]}** · {stored['decided_at']}"
        )
        if stored["analyst_notes"]:
            st.caption(stored["analyst_notes"])
        return

    st.caption(
        f"The agent's confidence is **{record['confidence_level']}**. It has made "
        "no disposition — this decision is yours."
    )
    notes = st.text_area("Notes (optional)", key=f"notes_{applicant_id}", height=80)

    def decide(decision: str) -> None:
        agent.record_analyst_decision(record["audit_log_id"], decision, notes or None)
        st.rerun()

    if st.button("✅ Approve", use_container_width=True):
        decide("approved")
    if st.button("🚫 Reject", use_container_width=True):
        decide("rejected")
    if st.button("🔍 Ask for more evidence", use_container_width=True):
        decide("escalated")


# --- page -------------------------------------------------------------------

def main() -> None:
    _require_current_agent_module()
    state = _state()

    try:
        cases = agent.list_cases()
    except FileNotFoundError as exc:
        st.error(str(exc))
        st.stop()

    if state.selected_case_id is None:
        state.selected_case_id = cases[0]["id"]
        _fill_brief(agent.get_case(state.selected_case_id))

    with st.sidebar:
        st.title("Settings")
        demo = st.toggle(
            "Demo mode",
            value=state.demo_mode,
            help="Runs the real loop, tools and audit trail against a canned "
                 "analyzer instead of a live model. No API key, no cost.",
        )
        if demo != state.demo_mode:
            state.demo_mode = demo
            st.rerun()
        if demo:
            st.caption(
                ":orange[No model call — the memo is assembled from real tool "
                "results, so the prose is not model-generated.]"
            )
        else:
            st.caption(
                "Live mode"
                + ("" if _has_credentials() else " · :red[no credentials found]")
            )

        transport, _ = agent.resolve_transport()
        st.caption(
            f"Transport: `{transport}`"
            + ("" if transport == "mcp" else " · gateway not running")
        )
        st.divider()
        st.caption(
            "The agent is advisory. It has no approve, reject or escalate tool — "
            "only the buttons on this page can set a disposition."
        )

    if not state.demo_mode and not _has_credentials():
        st.warning(
            "Live mode needs credentials: set `ANTHROPIC_API_KEY` (or run "
            "`ant auth login`), or switch on demo mode in the sidebar.",
            icon="🔑",
        )

    st.title("Synthetic Identity Investigation Copilot")

    case = agent.get_case(state.selected_case_id)
    chat_col, side_col = st.columns([2, 1], gap="large")

    with side_col:
        render_case_feed(cases, state.selected_case_id)
        st.divider()
        render_snapshot(case)
        st.divider()
        render_decision_panel(case["id"])
    with chat_col:
        render_chat_panel(case)


if __name__ == "__main__":
    main()
