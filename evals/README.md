# The investigation eval

Measures one flow: `agent.run_investigation(applicant_id, require_memo=True)` —
the agent picks its tools, works a flagged case, and submits a memo.

## Run it

```bash
python -m evals.run --approve-harness     # review the harness, record its sha
python -m evals.run --reps 3              # the real pass; spends money
```

Free checks that need no API key:

```bash
python -m evals.run --demo --reps 1       # wiring only, canned analyzer
python -m evals.run --no-judge            # programmatic metrics, live agent
python -m evals.estimate_cost --reps 3    # what a pass will cost
```

Then build the report (the deliverable — never read the raw JSON):

```bash
R="<claude-api skill base dir>/shared/evals/report"
node "$R/build-report-lite.mjs" .claude/hillclimb/investigation/
open .claude/hillclimb/investigation/report.html
```

## What it measures

| Metric | Kind | Meaning |
| --- | --- | --- |
| `confidence` | float | **Headline.** Ordinal against the expected tier: 1.0 exact, 0.5 one tier off, 0.0 two off |
| `guardrails` | float | 1.0 only if every structural check holds, else 0.0 |
| `evidence_cited` | float | Share of evidence items citing a tool that actually ran |
| `counter_narr` | judge | Share of four rubric claims the counter-narrative satisfies |

Scoring is ordinal rather than pass/fail because the errors are not equal:
calling a ring member `medium` is a worse miss than `high` and a far better one
than `low`. A binary pass rate throws that shape away, along with resolution the
eval needs.

The guardrail checks are the project's own promises, made testable: a
counter-narrative exists and is not a stub, the confidence level is in the enum,
no disposition language addressed to the analyst, and `analyst_decision` is still
NULL after the agent has run.

`evidence_cited` is the hallucination check — evidence attributed to a lookup
that never ran is the cheapest error to make and the most damaging thing to find
in an audit trail.

The runner also reports **false positives** separately: a legitimate applicant
graded high-confidence synthetic. On this product that is the error that matters
most, and an aggregate score hides it.

## Cases

50 cases — 17 `high`, 17 `low`, 16 `medium`. Six are the hand-built archetypes
from `db/seed.py`; forty-four are generated from specs in `db/eval_cases.py`.
Expected labels and the labeling policy live in `evals/cases.py`, deliberately
apart from the data they describe. Read [CASES.md](CASES.md) for the reviewable
table.

`low` means low confidence that the **identity is fabricated** — not that the
application is fine. Applicants 5, 18 and 40 are real people running
first-party abuse: correctly `low` here, still a problem for the lender.

Five rings (A–E) at tight velocity, four lone synthetics with no tight ring link
at all, thirteen legitimate files across ages and thin/mature shapes, four
adult-issuance cases with a benign cause recorded, and sixteen deliberately
ambiguous middles. The policy is machine-checked against every benign-cause
case, so a label and the policy cannot drift apart silently.

## Resolution — read this before acting on a result

The `1/sqrt(n·reps)` rule is a **conservative bound**: it assumes a binary
metric at maximum variance and independent samples. This eval's headline is
continuous and the comparisons that matter are paired, and both beat the bound.

| cases × reps | conservative bound |
| --- | --- |
| 50 × 2 | ±10 points |
| 50 × 3 | ±8 points |
| 50 × 5 | ±6 points |

On a 50 × 2 pass the *measured* half-width for a single config's mean already
came in at ±5.8 points against that ±10 bound — the continuous metric buys
roughly half the noise back.

Do not plan reps from the table. Run `python -m evals.power --target 0.05` after
a real pass: it reads the measured between-case and rep-to-rep variance and
reports how many reps a paired comparison needs to resolve the difference you
would act on. On deterministic demo rows it says so and declines to answer,
rather than returning a flattering number.

## Properties the runner has

Resume is idempotent at the `(case, rep)` key and rows are written as each case
completes, so a crash costs nothing already finished. Failed attempts go to
`errors.jsonl` with a failure class, never to `results.jsonl` — a row there
would make resume skip the case forever and would score plumbing as a model
failure. There is a hard per-case wall-clock ceiling, jittered backoff on 429 and
overloaded, and a served-model assertion: a silently substituted model
invalidates every comparison built on the run.

The harness-integrity gate refuses to run when `evals/run.py`, `evals/grade.py`,
`evals/cases.py`, or anything in `_state.json.harness_paths` has changed since
approval. Re-approving is yours to do, not the runner's — otherwise edited
scoring quietly makes rounds incomparable.
