# Synthetic Identity Investigation Copilot

An AI agent that investigates flagged synthetic-identity fraud cases, reconstructs how the
identity was matured, and writes an evidence-linked case memo with a counter-narrative — then
hands it to a human analyst. It never disposes of a case on its own.

All data is fabricated. Field shapes are modeled on real published formats (SentiLink's Synthetic
Score, Metro 2 tradeline fields) so the demo holds up under a practitioner's eye.

## Quickstart

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...     # or: ant auth login
python db/seed.py                       # build db/cases.db (--force to rebuild)
streamlit run app.py
```

Terminal alternative, same agent loop:

```bash
python investigate.py --list
python investigate.py 1
```

Offline check of the loop, tools and guardrails — no API key, no cost:

```bash
python -m tests.test_loop
```

## The guardrail

The agent is advisory. There is no approve, reject, or escalate tool — not a rule it is asked to
follow, but an absence in the tool list, so there is nothing for it to call. Its only write is
`submit_case_memo`, which inserts an `audit_log` row with `analyst_decision` left `NULL`. The one
code path that can set that column is `agent.record_analyst_decision`, reached only from the
buttons in the UI.

Every memo carries a confidence level rather than a verdict, and a counter-narrative arguing that
the applicant is a real person — because the signals that identify synthetics have innocent
versions. An SSN issued after the claimed birth date fits a fabricated identity; it also fits
someone who immigrated as an adult. An authorized-user tradeline is how synthetics are matured;
it is also how a parent helps a teenager build credit.

## The cases

Six fabricated applicants, built so the agent has something real to reason about:

| # | Applicant | Score | What it is |
| --- | --- | --- | --- |
| 1 | Marcus Delane Hoyt | 918 | Textbook matured synthetic; the anchor of a three-identity ring |
| 2 | Tressa Lindqvist | 874 | Same ring — shares an address, device and IP with #1 |
| 3 | Devon Aguayo-Pratt | 841 | Same ring — shares a phone with #1, already slipping past due |
| 5 | Oscar Bellweather | 766 | Real person, first-party bust-out: 20 clean years, then a stacking spree |
| 6 | Nadia Osei-Kwame | 538 | Real person who immigrated as an adult — the SSN mismatch is innocent |
| 4 | Priya Raghunathan | 402 | Real 22-year-old with a thin file and a parent's AU line |

4 and 6 are the ones worth watching: they score badly for legitimate reasons, so the
counter-narrative has to do actual work.

## How it works

1. The agent is given the flagged case, its score, and its reason codes.
2. It chooses tools based on what is suspicious about *this* case — not a fixed checklist. A case
   flagged for first-party abuse gets a different investigation from one flagged for a shared device.
3. After each result it decides whether it has enough or needs more.
4. Before submitting it self-checks: is every claim tied to a tool result, and is the
   counter-narrative substantive?
5. It calls `submit_case_memo` — timeline, evidence, counter-narrative, confidence level.

### Tools

| Tool | Reads | Returns |
| --- | --- | --- |
| `check_ssn_issuance` | `ssn_issuance_checks` | Whether the claimed DOB matches how/when the SSN was issued |
| `check_credit_trajectory` | `tradelines` | Account history in date order, with utilization |
| `check_authorized_user_history` | `tradelines` (`ecoa_code = authorized_user`) | Whether and when the identity was added to someone else's account |
| `check_shared_identifiers` | `shared_identifiers` | Phone/address/device/email/IP values also on other flagged applicants |
| `web_search` | live web | Fraud-pattern context (the only non-mocked tool) |
| `submit_case_memo` | writes `audit_log` | Saves the memo, ends the investigation |

Every SQLite tool takes only `applicant_id`, and only the id of the case under investigation —
anything else comes back as a tool error. An id is unambiguous where names and DOBs collide, the
model cannot mistype it into someone else's file, and it keeps personal data out of
`audit_log.tool_calls_made`. Inside each tool the code reads name, DOB and SSN from `applicants`
and builds a provider-shaped request itself, which is what a real provider call looks like.

## Layout

```
├── app.py              # Streamlit UI: feed, memo, decision buttons
├── investigate.py      # same loop, from the terminal
├── agent/
│   ├── loop.py         # tool-use loop with Claude
│   ├── tools.py        # tool definitions + implementations
│   └── db.py           # the only module that touches SQLite
├── db/
│   ├── schema.sql
│   └── seed.py         # generates the mock cases
└── tests/test_loop.py  # offline smoke test, stubbed client
```

The UI only imports `agent`. That package is the single point that calls Claude, runs tools, and
writes to the database.

## Stack notes

- **Model:** `claude-opus-5` with adaptive thinking. Server-side refusal fallbacks are enabled;
  drop `betas` / `fallbacks` in `agent/loop.py` to turn that off.
- **Manual tool-use loop**, not the SDK's tool runner: the UI needs an event per step to drive
  `st.status`, `web_search` can end a turn with `pause_turn` (which the Python runner does not
  auto-resume), and `submit_case_memo` has to terminate the loop rather than feed a result back.
- **No embeddings, no vector database, no RAG.** Every lookup is structured and exact-match.
