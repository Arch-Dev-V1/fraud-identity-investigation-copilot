# Synthetic Identity Investigation Copilot — project brief

## What this is
A portfolio POC: an AI agent that investigates flagged synthetic-identity fraud cases
(all data is synthetic), reconstructs a maturation timeline, writes an evidence-linked
case memo with a counter-narrative, and hands it to a human analyst for approval —
it never disposes a case on its own.

## Stack
- Frontend + backend: Python + Streamlit, one app. `st.status` handles live
  step-by-step updates, so no separate server or SSE plumbing is needed.
- Reasoning core: Claude API with tool use — the model decides which tools to call
  and when, based on the case in front of it, not a fixed script. Model is
  `claude-opus-5` with adaptive thinking; see `agent/loop.py`.
- Data: SQLite (see db/schema.sql). No vector database, no RAG. All lookups are
  structured/exact-match; the one live tool is real web search, used for current
  fraud-pattern context.

## Project structure
```
synthetic-id-copilot/
├── CLAUDE.md
├── README.md
├── app.py              # Streamlit UI: feed, memo, decision buttons
├── investigate.py      # the same agent loop, driven from the terminal
├── agent/
│   ├── loop.py         # tool-use loop with Claude
│   ├── tools.py        # tool definitions + implementations
│   ├── demo.py         # canned analyzer for no-key demo mode
│   └── db.py           # the only module that opens the SQLite file
├── db/
│   ├── schema.sql
│   └── seed.py         # generates the mock cases
└── tests/
    └── test_loop.py    # offline smoke test against a stubbed client
```
The UI only talks to the agent module. The agent module is the single point that
calls Claude, runs tools, and writes to the database.

## Data model
See db/schema.sql. Two fields worth knowing going in:
- `tradelines.ecoa_code` is modeled on the real Metro 2 field lenders use to report
  accounts to credit bureaus — it captures an "authorized user" credit-boost
  relationship.
- `applicants.claimed_email` exists because real scoring providers take email as
  an input alongside name, DOB, SSN, phone, and address.
- `shared_identifiers.identifier_type` covers `phone`, `address`, `device_id`,
  `email`, and `ip_address`. Fraud rings can invent names and SSNs cheaply but tend
  to reuse an email or an IP, so these are often the strongest links between
  applications. IP is stored only here, not on `applicants`, because it describes
  where an application came from, not something the person has.
- `scores` is modeled on SentiLink's published Synthetic Score shape: 0-999,
  first-party / third-party / composite abuse sub-scores, a risk tier, and reason
  codes.

## Tools the agent can call
| Tool | Input | Reads | Returns |
| --- | --- | --- | --- |
| `check_ssn_issuance` | applicant_id | ssn_issuance_checks | Whether the claimed DOB matches how/when the SSN was issued |
| `check_credit_trajectory` | applicant_id | tradelines | Account history in date order: open dates, limits, balances, status |
| `check_authorized_user_history` | applicant_id | tradelines (ecoa_code = authorized_user) | Whether and when the identity was added to someone else's account |
| `check_shared_identifiers` | applicant_id | shared_identifiers | Phone, address, device, email, or IP values that also appear on other flagged applicants (exact match only) |
| `web_search` | query | live web | General fraud-pattern context (e.g. known mail-drop address types) |
| `submit_case_memo` | timeline, evidence, counter_narrative, confidence_level | writes audit_log | Saves the memo and ends the investigation |

Notes on the tools:
- Every SQLite tool takes only `applicant_id` as input, on purpose. An ID is
  unambiguous (names and DOBs collide), the model can't mistype it, and it keeps
  personal data out of `audit_log.tool_calls_made`. The agent still sees the
  applicant's details in its opening prompt; it just doesn't pass them back to
  look things up.
- Inside each tool, the code reads name, DOB, SSN, etc. from `applicants` and
  builds a provider-shaped request itself. This keeps the mock looking like a real
  provider call (real providers take attributes, not our internal ID) while the
  agent only handles one safe value.
- A tool should only accept the applicant_id of the case under investigation.
  Enforced in `agent/tools.execute_tool`: any other id returns a tool error.
- The first four are read-only lookups against SQLite. `web_search` is the only
  non-mocked tool.
- `submit_case_memo` is the agent's only write. It creates the audit_log row with
  `analyst_decision` left NULL.
- There is deliberately no approve, reject, or escalate tool. The agent has no way
  to make the decision; only the analyst's button in the UI can.

## Agent loop
1. Agent receives the flagged case, its score, and its reason codes.
2. Agent decides which tool(s) to call next based on what is actually suspicious
   about this specific case — not a fixed checklist order.
3. After each result it decides whether it has enough evidence or needs more.
4. Before submitting, it self-checks: is the evidence strong enough, and is the
   counter-narrative genuinely substantive? If thin, it goes back for more.
5. It calls `submit_case_memo`: timeline, evidence, counter-narrative, and a
   confidence level — never a bare yes/no verdict.

Implemented as a manual tool-use loop rather than the SDK's tool runner: the UI
needs an event per step to drive `st.status`, `web_search` can end a turn with
`pause_turn` (which the Python runner does not auto-resume), and
`submit_case_memo` has to terminate the loop rather than feed a result back.
The loop is a generator and never imports Streamlit, so `investigate.py` and the
tests drive the same code the UI does.

## Demo mode (non-negotiable)
The app must run end to end with no API key, so that development and testing never
incur API cost. Demo mode (`agent/demo.py`) replaces only the model: the real loop,
the real tools, the real database writes and every guardrail still apply, and the
memo is assembled from actual tool results by a canned analyzer. Demo memos are
labelled as canned in the UI and in `audit_log` so they cannot be mistaken for real
ones. It defaults on when no credentials are present; `DEMO_MODE=1`, the sidebar
toggle and `investigate.py --demo` force it. In live mode a key is required, and its
absence is reported rather than swallowed.

Any new agent behaviour must be exercisable offline — through demo mode or the
stubbed client in `tests/test_loop.py` — not only against the live API.

## Guardrails (non-negotiable)
- Advisory only — the agent recommends; it never closes, rejects, or escalates a
  case by itself.
- Every case memo must include a counter-narrative, not just the suspicious story.
- Confidence level, not a binary verdict.
- Full evidence and tool-call trail logged to `audit_log`.
- `audit_log.analyst_decision` stays NULL until a human sets it — enforced
  structurally in the schema and by the absence of any decision tool, not just as
  an app-level rule that could be forgotten. The only writer is
  `agent.record_analyst_decision`, called from the UI buttons.

## UI layout
Two panels. Left: live investigation status feed, settling into the case memo.
Right: case snapshot (name, score, risk tier) and the decision buttons
(Approve / Reject / Ask for more evidence) — always visible, no scrolling needed
to find them.

## Explicitly not needed for this POC
No embeddings, no vector database, no RAG, no live regulated data, no vendor
benchmarking. Everything runs on fabricated data built for this demo.
