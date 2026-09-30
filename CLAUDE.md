# Synthetic Identity Investigation Copilot — project brief

## What this is
A portfolio POC: an AI agent that investigates flagged synthetic-identity fraud cases
(all data is synthetic), reconstructs a maturation timeline, writes an evidence-linked
case memo with a counter-narrative, and hands it to a human analyst for approval —
it never disposes a case on its own.

## Stack
- Frontend: Python + Streamlit. `st.status` handles live step-by-step updates,
  so no SSE plumbing is needed.
- Data access is layered: a FastAPI provider gateway stands in for real vendor
  APIs, an MCP server publishes the lookups as MCP tools, and the agent is an
  MCP client. See "Layers and transports" below.
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
├── run.sh              # starts the gateway, then the app
├── agent/
│   ├── loop.py         # tool-use loop with Claude
│   ├── tools.py        # tool definitions, transports, scope guard
│   ├── mcp_bridge.py   # sync facade over the async MCP client
│   ├── demo.py         # canned analyzer for no-key demo mode
│   └── db.py           # case feed, memo write, analyst decision
├── provider_api/
│   ├── main.py         # FastAPI vendor gateway (HTTP transport)
│   ├── lookups.py      # lookup logic both transports share
│   └── metro2.py       # ECOA + payment-history field helpers
├── mcp_server/
│   └── server.py       # the four lookups as MCP tools
├── db/
│   ├── schema.sql
│   └── seed.py         # generates the mock cases
└── tests/
    └── test_loop.py    # offline: loop, demo mode, MCP transport
```
The UI only talks to the agent module. The agent module is the single point that
calls Claude, runs tools, and writes to the database.

Import direction is one-way: `agent` may import `provider_api`, never the
reverse. `provider_api` and `mcp_server` must not import `agent` — that cycle
has already been introduced once and broken.

## Layers and transports
```
UI -> agent -> mcp_server (stdio) -> provider_api (HTTP) -> SQLite
```
- `provider_api/` is the mock vendor. Real providers are HTTP services taking
  identity attributes, so each endpoint returns the attribute-shaped payload it
  would have sent under a `request` key. Logic lives in `lookups.py`; `main.py`
  is only transport.
- `mcp_server/` publishes the four lookups as MCP tools so any MCP client can
  use them. The tools are thin HTTP clients by design.
- Two transports: `TOOL_TRANSPORT=mcp` (default) is the path above;
  `direct` calls `provider_api.lookups` in-process so demo mode and the tests
  run with nothing started. Both call the SAME lookup functions — a test
  asserts the payloads are identical, because if the paths built their own SQL
  the agent would see different evidence depending on its wiring.
- MCP selected but gateway down falls back to `direct` with a visible note. A
  fallback must never be silent.
- `submit_case_memo` is NOT on the MCP surface. It is not a lookup, and putting
  the memo write on a shared tool surface would let any MCP client write to the
  audit log.
- The scope guard lives agent-side in `tools.execute_tool`, before any
  transport: only the agent knows which case is open, and a generic tool
  surface must not be trusted to enforce it.

## Data model
See db/schema.sql. Fields worth knowing going in:
- `tradelines.ecoa_code` uses the REAL Metro 2 single-character domain: '1'
  individual, '2' joint contractually liable, '3' authorized user. Never compare
  characters inline — go through `provider_api/metro2.py`.
- `tradelines.payment_history_profile` is the real Metro 2 24-character field,
  one char per month, most recent first ('0' current .. '6' 180+ days, 'B' for
  months before the account existed). It is what makes a bust-out visible;
  balances alone cannot show one.
- `ssn_verification_checks` keeps two distinct real signals apart, and this
  matters: `ecbsv_match` is all eCBSV actually returns (SSA match on SSN + name
  + DOB, nothing about issuance), while `ssn_first_observed` is the separate
  identity-graph signal. SSA randomized number assignment on 2011-06-25, so an
  issuance era is NOT derivable from a modern number — an earlier version of
  this schema wrongly implied eCBSV returned one. Every seeded case passes
  eCBSV; that is the sharper story.
- `shared_identifiers.first_seen` / `last_seen` carry velocity, and the gateway
  derives a `span_days` per value. It cuts both ways on purpose: the ring's
  device and IP span 11 days across three applicants, its address spans 285.
- `scores.reason_codes` follows SentiLink's structure; the code strings are
  ours, not their published vocabulary. Keep them obviously ours.
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
| `check_ssn_verification` | applicant_id | ssn_verification_checks | eCBSV match, and separately when the SSN first appears in header data |
| `check_credit_trajectory` | applicant_id | tradelines | Accounts in date order with Metro 2 fields and 24-month payment history |
| `check_authorized_user_history` | applicant_id | tradelines (ecoa_code = '3') | Whether and when the identity was added to someone else's account |
| `check_shared_identifiers` | applicant_id | shared_identifiers | Matching phone/address/device/email/IP with sighting dates and velocity |
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
- The first four are read-only lookups, reached over MCP or in-process.
  `web_search` is the only non-mocked tool.
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

The loop runs one turn at a time and is conversational. `run_investigation`
takes `user_message` (the analyst's message; omitted, the generated case brief
is used), `history` (the prior turns, handed back by the `turn_complete` event),
and `require_memo`. `require_memo=True` is the Run-investigation path and nudges
a turn that ends without a memo; `False` is an ordinary chat message, where a
plain text answer is a complete response — asking what ECOA 3 means must not
force a memo, and must not write to `audit_log`.

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
Two panels, chat-first.

Left — the conversation with the agent: the message transcript, the live
investigation feed while a turn runs, then the composer with **Run
investigation** and **Send** directly below it. Memos appear in the transcript
as the agent's reply, so the results read as part of the conversation rather
than a separate pane.

Right — the flagged-case feed (selected case highlighted), the snapshot for
whichever case is selected (score, sub-scores, applicant details, reason codes),
and the decision buttons (Approve / Reject / Ask for more evidence).

Selecting a case drops that case's brief into the composer, so the analyst can
send it as-is, edit it, or add a question. A brief is only inserted when the
composer is empty or still holds an unedited brief — a typed draft is never
discarded, and **Refill brief** loads it deliberately.

Two things about the composer that are easy to get wrong:
- Its text lives in `composer_draft`, not in the widget's key. Streamlit forbids
  writing a widget's key after that widget has been instantiated, and the send
  buttons render below the box, so clearing it on send requires rotating the
  widget key (`composer_nonce`) instead.
- The rows from `list_cases()` are feed summaries with no `claimed_dob`. Build a
  brief from `get_case()`, never from a feed row.

No model or vendor name appears anywhere in the UI. Keep it that way — the
sidebar says "Live mode" or "Demo mode", not which model is behind it.

## Explicitly not needed for this POC
No embeddings, no vector database, no RAG, no live regulated data, no vendor
benchmarking. Everything runs on fabricated data built for this demo.

Deliberately out of scope in the data, and why: inquiry velocity, email tenure,
phone line-type, watchlist screening, CMRA / mail-drop flags, and the remaining
~33 Metro 2 base-segment fields. Each adds a table and possibly a tool for one
marginal signal; the agent already reasons over four evidence types in visibly
different orders per case.
