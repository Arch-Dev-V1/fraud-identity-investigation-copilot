"""Synthetic Identity Investigation Copilot — analyst UI.

Two panels. Left: the live investigation feed, settling into the case memo.
Right: the case snapshot and the decision buttons, always visible.

This file only talks to the `agent` module. It has no database access and no
Claude access of its own.
"""

from __future__ import annotations

import json
import os

import streamlit as st

import agent

st.set_page_config(
    page_title="Synthetic Identity Investigation Copilot",
    page_icon="🕵️",
    layout="wide",
)

TIER_COLOR = {"high": "🔴", "medium": "🟠", "low": "🟡"}
DECISION_LABEL = {
    "approved": "Approved",
    "rejected": "Rejected",
    "escalated": "Escalated for more evidence",
}
TOOL_LABEL = {
    "check_ssn_issuance": "Checking SSN issuance against claimed DOB",
    "check_credit_trajectory": "Pulling credit trajectory",
    "check_authorized_user_history": "Checking authorized-user history",
    "check_shared_identifiers": "Looking for identifiers shared with other flagged applications",
    "web_search": "Searching for fraud-pattern context",
}


# --- state ------------------------------------------------------------------

def _state():
    st.session_state.setdefault("selected_case_id", None)
    st.session_state.setdefault("runs", {})       # applicant_id -> run record
    st.session_state.setdefault("pending_run", None)
    return st.session_state


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


# --- rendering --------------------------------------------------------------

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


def run_investigation_ui(applicant_id: int, case: dict) -> bool:
    """Drive the agent loop, streaming each step into st.status.

    Returns True if a memo was submitted. On failure it returns False and
    leaves the error on screen — the caller must not rerun over it.
    """
    events: list[dict] = []
    record: dict | None = None

    with st.status(f"Investigating {case['name']}…", expanded=True) as status:
        try:
            for event in agent.run_investigation(applicant_id):
                events.append(event)
                if event["type"] == "start":
                    st.markdown(
                        f"Flagged at **{case['abuse_score']}** "
                        f"({case['risk_tier']} risk) · reason codes "
                        f"`{case['reason_codes']}`"
                    )
                    continue
                if event["type"] == "memo":
                    record = {
                        "events": events,
                        "markdown": event["markdown"],
                        "memo": event["memo"],
                        "audit_log_id": event["audit_log_id"],
                        "confidence_level": event["memo"]["confidence_level"],
                        "trail": event["trail"],
                    }
                    st.markdown("**Case memo submitted.**")
                    continue
                render_event(event, st)
        except Exception as exc:  # keep the UI alive on an unexpected failure
            status.update(label=f"Investigation failed: {exc}", state="error")
            st.exception(exc)
            return False

        if record is None:
            status.update(label="Investigation ended without a memo", state="error")
            return False
        status.update(label=f"Investigation complete — {case['name']}", state="complete")

    _state().runs[applicant_id] = record
    return True


def render_memo_panel(applicant_id: int, case: dict) -> None:
    record = _run_record(applicant_id)

    if _state().pending_run == applicant_id:
        _state().pending_run = None
        if run_investigation_ui(applicant_id, case):
            st.rerun()
        # Failed: the status box above holds the reason. Rerunning here would
        # wipe it and leave the analyst staring at an empty panel.
        return

    if record is None:
        st.info(
            "No investigation has been run on this case yet. "
            "Use **Run investigation** on the right to start one."
        )
        return

    if record.get("from_disk"):
        st.caption("Showing the most recent memo on file for this applicant.")

    st.markdown(record["markdown"])

    if record.get("events"):
        with st.expander("Investigation steps", expanded=False):
            render_step_replay(record["events"])

    with st.expander("Tool-call trail (audit_log)", expanded=False):
        st.caption(
            f"audit_log row {record['audit_log_id']} · "
            f"{len(record['trail'])} tool call(s) recorded"
        )
        st.json(record["trail"])


def render_decision_panel(applicant_id: int, case: dict) -> None:
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
    st.caption("Reason codes")
    st.code("\n".join(case["reason_codes"].split(",")), language=None)
    st.caption(
        f"DOB {case['claimed_dob']} · {case['claimed_phone']}  \n"
        f"{case['claimed_address']}  \n{case['claimed_email']}"
    )

    st.divider()

    record = _run_record(applicant_id)
    running = _state().pending_run is not None

    if st.button(
        "Run investigation" if record is None else "Re-run investigation",
        type="primary" if record is None else "secondary",
        use_container_width=True,
        disabled=running,
    ):
        _state().runs.pop(applicant_id, None)
        _state().pending_run = applicant_id
        st.rerun()

    st.divider()
    st.markdown("#### Analyst decision")

    if record is None:
        st.caption("Available once a case memo has been submitted.")
        return

    stored = agent.get_memo(record["audit_log_id"])
    if stored and stored["analyst_decision"]:
        st.success(
            f"**{DECISION_LABEL[stored['analyst_decision']]}** · "
            f"{stored['decided_at']}"
        )
        if stored["analyst_notes"]:
            st.caption(stored["analyst_notes"])
        return

    st.caption(
        f"The agent's confidence is **{record['confidence_level']}**. "
        "It has made no disposition — this decision is yours."
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
    state = _state()

    try:
        cases = agent.list_cases()
    except FileNotFoundError as exc:
        st.error(str(exc))
        st.stop()

    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        st.warning(
            "No `ANTHROPIC_API_KEY` in the environment. Set one (or run "
            "`ant auth login`) before starting an investigation.",
            icon="🔑",
        )

    with st.sidebar:
        st.title("Flagged cases")
        st.caption("All data is fabricated for this demo.")
        for case in cases:
            marker = TIER_COLOR.get(case["risk_tier"], "")
            decided = f" · {DECISION_LABEL[case['latest_decision']]}" if case["latest_decision"] else ""
            if st.button(
                f"{marker} **{case['name']}** — {case['abuse_score']}{decided}",
                key=f"case_{case['id']}",
                use_container_width=True,
            ):
                state.selected_case_id = case["id"]
                st.rerun()
        st.divider()
        st.caption(f"Model: `{agent.MODEL}`")
        st.caption(
            "The agent is advisory. It has no approve, reject or escalate tool — "
            "only the buttons on this page can set a disposition."
        )

    if state.selected_case_id is None:
        state.selected_case_id = cases[0]["id"]

    case = agent.get_case(state.selected_case_id)

    st.title("Synthetic Identity Investigation Copilot")

    feed_col, decision_col = st.columns([2, 1], gap="large")
    with decision_col:
        render_decision_panel(case["id"], case)
    with feed_col:
        render_memo_panel(case["id"], case)


if __name__ == "__main__":
    main()
