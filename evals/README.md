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

25 cases — 9 `high`, 9 `low`, 7 `medium`. Six are the hand-built archetypes from
`db/seed.py`; nineteen are generated from specs in `db/eval_cases.py`. Expected
labels and the labeling policy live in `evals/cases.py`, deliberately apart from
the data they describe. Read [CASES.md](CASES.md) for the reviewable table.

`low` means low confidence that the **identity is fabricated** — not that the
application is fine. Applicants 5 and 18 are real people running first-party
abuse: correctly `low` here, still a problem for the lender.

## Resolution — read this before acting on a result

At 25 cases the noise floor on the headline is roughly `1/sqrt(n × reps)`:

| reps | noise floor |
| --- | --- |
| 2 | ±14 points |
| 3 | ±12 points |
| 5 | ±9 points |

The published effort curves move 1–3 points on research-shaped work, and the
Opus 5.5 comparison maybe 2–8. **So this eval is a reliable regression guard and
not a reliable instrument for the effort sweep.** Treat sweep results as
directional, or raise cases and reps together before trusting a small delta.

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
