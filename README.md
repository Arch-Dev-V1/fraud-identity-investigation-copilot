# Synthetic Identity Investigation Copilot

An AI agent that investigates flagged synthetic-identity fraud cases, reconstructs how the
identity was matured, and writes an evidence-linked case memo with a counter-narrative — then
hands it to a human analyst. It never disposes of a case on its own.

All data is fabricated. Field shapes follow real published formats (SentiLink's Synthetic Score,
Metro 2 base-segment fields, eCBSV's actual response) so the demo holds up under a
practitioner's eye.

## Quickstart

```bash
python3 -m venv .venv                   # Python 3.10+
source .venv/bin/activate               # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python db/seed.py                       # build db/cases.db (--force to rebuild)
./run.sh                                # gateway + app, on http://localhost:8501
```

`run.sh` starts the provider gateway and then Streamlit. The MCP server is not in that list
because the agent launches it itself over stdio. To run the pieces by hand:

```bash
python -m uvicorn provider_api.main:app --port 8000     # provider gateway
streamlit run app.py                                    # the app
```

**No API key needed.** With no credentials present the app starts in demo mode and the whole
flow works end to end. For live investigations:

```bash
export ANTHROPIC_API_KEY=sk-ant-...     # or: ant auth login
```

## Architecture

```
                    ┌──────────────────────────────────────────┐
   Streamlit UI ──▶ │ agent/  loop · tools · demo · db         │
                    └───────────────┬──────────────────────────┘
                                    │  tool_use  (scope guard here)
                                    ▼
                    ┌──────────────────────────────────────────┐
                    │ mcp_server/   MCP tool surface (stdio)   │
                    └───────────────┬──────────────────────────┘
                                    │  HTTP
                                    ▼
                    ┌──────────────────────────────────────────┐
                    │ provider_api/  mock vendor gateway       │
                    │                lookups · metro2          │
                    └───────────────┬──────────────────────────┘
                                    ▼
                                 SQLite
```

Each layer has a distinct job rather than being a pass-through:

- **`provider_api/`** stands in for the vendor APIs a lender actually integrates. SentiLink,
  Socure and LexisNexis are all HTTP services that take identity *attributes*, so every endpoint
  returns the attribute-shaped payload it would have sent under a `request` key — the provider
  contract stays visible instead of implied. `provider_api/lookups.py` holds the logic;
  `main.py` is only transport.
- **`mcp_server/`** publishes the four lookups as MCP tools, so anything that speaks MCP can use
  them — this app's agent, Claude Desktop, another team's agent. The tools are deliberately thin:
  they call the gateway and return JSON.
- **`agent/`** owns the tool-use loop, the memo, and the guardrail.

**Two transports.** `TOOL_TRANSPORT=mcp` (default) is the path above. `TOOL_TRANSPORT=direct`
calls `provider_api.lookups` in-process, which is how demo mode and the tests run with nothing
else started. Both transports call the *same* lookup functions, so their responses are identical
by construction — a test asserts this, because if the two paths built their own SQL the agent
would see different evidence depending on how it was wired. If MCP is selected but the gateway
isn't reachable, the agent falls back to direct and says so in the UI rather than silently.

**What is not on the MCP surface:** `submit_case_memo`, and anything that could decide a case.
The memo write is not a lookup, and exposing it on a shared tool surface would let any MCP client
write to the audit log. It stays in-process next to the guardrail it depends on.

**Where the scope guard lives:** agent-side, in `agent/tools.execute_tool`, before any transport.
Only the agent knows which case is open, and the MCP server is a generic surface that must not be
trusted to enforce it. A test checks the guard holds over MCP as well as in-process.

## Seeing the HTTP traffic

Four ways, depending on what you want to look at.

**Poke the endpoints by hand — Swagger UI.** FastAPI generates it, so it is
already there whenever the gateway is running:

```
http://127.0.0.1:8000/docs        interactive — "Try it out" runs a real request
http://127.0.0.1:8000/redoc       read-only reference
http://127.0.0.1:8000/openapi.json
```

**Read one payload in the terminal.**

```bash
python probe.py 1                  # every lookup for applicant 1
python probe.py 3 --only shared    # just the shared-identifier response
python probe.py 1 --compact        # status and size only
curl -s localhost:8000/v1/applicants/1/ssn-verification | python -m json.tool
```

**Watch the agent's calls arrive while you use the app.** `run.sh` leaves
uvicorn access logs on, so every request the agent makes appears in the gateway
console. For more than a status line, set the trace flag:

```bash
PROVIDER_API_TRACE=1    ./run.sh    # method, path, status, duration, size
PROVIDER_API_TRACE=body ./run.sh    # the same, plus each response body
```

With `=body`, starting an investigation prints the full provider response as the
agent receives it:

```
  → GET /v1/applicants/6/ssn-verification 200 · 1ms · 534B
      {
        "request": { "name": "Nadia Osei-Kwame", "ssn": "588-71-4402", ... },
        "result": {
          "ecbsv_match": true,
          "ssn_first_observed": "2021-10",
          "dob_consistent_with_header": false,
          ...
```

Tracing is off by default on purpose: these bodies carry names, SSNs and
addresses. They are fabricated here, but a gateway that logs provider responses
in full is not something you would ship, so it stays opt-in.

**See what the agent actually saw.** In the app, expand **result from
`<tool>`** in the investigation feed, or **Tool-call trail (audit_log)** under a
finished memo. On the MCP transport those payloads *are* the HTTP response
bodies, passed through unchanged — so that expander is the agent's-eye view of
the same traffic, and the trail is the persisted copy.

## Using the MCP server from other clients

It also serves over HTTP:

```bash
python -m mcp_server --transport streamable-http
```

Or over stdio, which is what an MCP client config looks like:

```json
{
  "mcpServers": {
    "synthetic-identity-lookups": {
      "command": "/path/to/.venv/bin/python",
      "args": ["-m", "mcp_server"],
      "env": { "PROVIDER_API_URL": "http://127.0.0.1:8000" }
    }
  }
}
```

The gateway must be running either way — the MCP tools are HTTP clients.

## Demo mode — the full flow at zero cost

Demo mode replaces exactly one thing: Claude. The real loop runs, the real tools resolve over the
real transport, the real `audit_log` row is written, and every guardrail applies — the memo is
assembled by a canned analyzer from actual tool results instead of being reasoned out by a model.
It is labelled as canned in the UI and in `audit_log`, so a demo memo can never be mistaken for a
real one.

It is on by default whenever no credentials are present, so the app is never a dead end. Force it
with the sidebar toggle, `DEMO_MODE=1`, or `investigate.py --demo`. With demo mode off and no key,
the app says so and refuses to start rather than failing silently.

Demo mode and transport are independent: demo mode works over MCP when the gateway is up, and
falls back to direct when it isn't.

What demo mode does **not** cover is the reasoning — which tools the agent chooses and what it
makes of the results. That needs a key.

## Using it

The app is chat-first. Left is the conversation with the agent; right is the
flagged-case feed and the case snapshot.

Selecting a case drops its brief into the composer. From there:

- **Run investigation** sends that brief as an investigation request. The agent
  picks its own tools, works the case, and submits a memo — which appears in the
  transcript as its reply, with the step-by-step feed and the audit trail
  expandable beneath it.
- **Send** is an ordinary message. Ask what a reason code means, or push back on
  a finding, and you get an answer without forcing a memo.
- Conversation history carries across turns, so you can follow up on a memo the
  agent just wrote.
- **Refill brief** reloads the selected case's brief; **Clear chat** starts the
  case over. A draft you have typed is never overwritten by switching cases.

The decision buttons sit on the right under the snapshot and unlock once a memo
exists. Free-form chat needs a live model; demo mode answers investigation
requests and says plainly that it cannot answer open questions.

## The guardrail

The agent is advisory. There is no approve, reject, or escalate tool — not a rule it is asked to
follow, but an absence in the tool list, so there is nothing for it to call. Its only write is
`submit_case_memo`, which inserts an `audit_log` row with `analyst_decision` left `NULL`. The one
code path that can set that column is `agent.record_analyst_decision`, reached only from the
buttons in the UI.

Every memo carries a confidence level rather than a verdict, and a counter-narrative arguing that
the applicant is a real person — because the signals that identify synthetics all have innocent
versions.

## The cases

| # | Applicant | Score | What it is |
| --- | --- | --- | --- |
| 1 | Marcus Delane Hoyt | 918 | Matured synthetic; anchor of a three-identity ring |
| 2 | Tressa Lindqvist | 874 | Same ring — shares an address, device and IP with #1 |
| 3 | Devon Aguayo-Pratt | 841 | Same ring — shares a phone with #1, already past due |
| 5 | Oscar Bellweather | 766 | Real person, first-party bust-out: 20 clean years, then a stacking spree |
| 6 | Nadia Osei-Kwame | 538 | Real person who immigrated as an adult — the missing history is innocent |
| 4 | Priya Raghunathan | 402 | Real 22-year-old, thin file, parent's authorized-user line |

4 and 6 are the ones worth watching: they score badly for legitimate reasons, so the
counter-narrative has to do real work. 5 is the one where the right answer is *low* confidence
that the identity is synthetic while the abuse risk is still real.

## Data fidelity — what is real and what is ours

Worth being explicit, since the point of the field shapes is that they survive scrutiny:

**Modeled on real formats.**
- `tradelines.ecoa_code` uses the real Metro 2 single-character domain: `1` individual, `2` joint
  contractually liable, `3` authorized user. Read it through `provider_api/metro2.py`, never by
  comparing characters.
- `tradelines.payment_history_profile` is the real Metro 2 field: 24 characters, one per month,
  most recent first, `0` current through `6` for 180+ days, `B` for months before the account
  existed. It is the richest single field for bust-out detection, which balances alone cannot show.
- `ssn_verification_checks` keeps two genuinely distinct signals apart. `ecbsv_match` is what
  eCBSV actually returns — a match of SSN + name + DOB against SSA records, and *nothing about
  issuance*. `ssn_first_observed` is the separate identity-graph signal: the earliest date the SSN
  appears in credit-header data. This distinction matters because SSA randomized number assignment
  on 2011-06-25, destroying the area/group encoding that once let you infer an issuance era from
  the number itself. All five ring and false-positive cases *pass* eCBSV, which is the sharper
  story: a match rules out a crude fabrication, not a patient one.
- `shared_identifiers.first_seen` / `last_seen` give velocity. The gateway computes a `span_days`
  per identifier value, which cuts both ways — the ring's device and IP appear across three
  applications inside 11 days, while its shared address spans 285 days and is argued as the weaker
  signal it is.
- `scores` mirrors SentiLink's published Synthetic Score shape: 0-999, first-party / third-party /
  composite, risk tier, reason codes.

**Ours, not theirs.** The reason-code strings (`SSN_HEADER_MISMATCH`, …) are invented. The
structure follows SentiLink's; the vocabulary does not. Codes that are obviously ours beat codes
that merely look official.

**Still absent.** Inquiry velocity, email tenure, phone line-type, watchlist screening, CMRA /
mail-drop flags, and the remaining ~33 Metro 2 base-segment fields. Each would add a table and a
tool for one marginal signal; the agent already reasons over four evidence types in visibly
different orders per case.

## Tools

| Tool | Reads | Returns |
| --- | --- | --- |
| `check_ssn_verification` | `ssn_verification_checks` | eCBSV match, and separately when the SSN first appears in header data |
| `check_credit_trajectory` | `tradelines` | Accounts in date order with Metro 2 fields and 24-month payment history |
| `check_authorized_user_history` | `tradelines` (ECOA `3`) | Whether and when the identity was added to someone else's account |
| `check_shared_identifiers` | `shared_identifiers` | Matching phone/address/device/email/IP with sighting dates and velocity |
| `web_search` | live web | Fraud-pattern context (the only non-mocked tool) |
| `submit_case_memo` | writes `audit_log` | Saves the memo, ends the investigation |

Every lookup takes only `applicant_id`, and only the id of the case under investigation — anything
else returns a tool error. An id is unambiguous where names and DOBs collide, the model cannot
mistype it into someone else's file, and it keeps personal data out of
`audit_log.tool_calls_made`.

## Layout

```
├── app.py                    # Streamlit UI: chat, case feed, decision buttons
├── investigate.py            # same loop, from the terminal
├── probe.py                  # call the gateway directly, print the response
├── run.sh                    # gateway + app
├── agent/
│   ├── loop.py               # tool-use loop with Claude
│   ├── tools.py              # tool definitions, transports, scope guard
│   ├── mcp_bridge.py         # sync facade over the async MCP client
│   ├── demo.py               # canned analyzer for no-key demo mode
│   └── db.py                 # case feed, memo write, analyst decision
├── provider_api/
│   ├── main.py               # FastAPI vendor gateway
│   ├── lookups.py            # the lookup logic both transports share
│   └── metro2.py             # ECOA + payment-history field helpers
├── mcp_server/
│   └── server.py             # the four lookups as MCP tools
├── db/
│   ├── schema.sql
│   └── seed.py               # generates the mock cases
└── tests/test_loop.py        # offline: loop, demo mode, MCP transport
```

## Restart after editing `agent/`

Streamlit re-runs `app.py` when it changes, but it does not reload local modules
it has already imported. So an edit under `agent/`, `provider_api/` or
`mcp_server/` does not reach a running server — you get a new `app.py` calling
an old `agent`, which shows up as a `TypeError` about an unexpected keyword
argument. Stop the server and start it again.

`app.py` checks for this on startup and says so plainly rather than letting the
`TypeError` surface.

## Verification

```bash
python -m tests.test_loop     # no API key, no cost, no network
```

Covers the loop against a stubbed client (tool results returned under the right `tool_use_id`,
`pause_turn` resumed, scope guard, one `audit_log` row with `analyst_decision` NULL), demo mode on
three cases, and the MCP transport in-process — including that both transports return byte-identical
payloads.

## Stack notes

- **Model:** `claude-opus-5` with adaptive thinking. Server-side refusal fallbacks are on; drop
  `betas` / `fallbacks` in `agent/loop.py` to disable.
- **Manual tool-use loop**, not the SDK's tool runner: the UI needs an event per step to drive
  `st.status`, `web_search` can end a turn with `pause_turn` (which the Python runner does not
  auto-resume), and `submit_case_memo` has to terminate the loop rather than feed a result back.
- **`agent/mcp_bridge.py`** runs the async MCP client on one long-lived coroutine in a background
  thread. Entering an MCP session in one task and calling it from another raises anyio
  cancel-scope errors, so enter, call and exit all happen in a single task serviced by a queue.
- **No embeddings, no vector database, no RAG.** Every lookup is structured and exact-match.
