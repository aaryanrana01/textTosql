# Evaluation results

This file records every evaluation run of the text-to-SQL pipeline. Each row shows what changed and its measured effect, which forms the project's ablation table.

## The benchmark

| Group | Count | What it tests |
|---|---|---|
| Easy | 15 | Single-table counts, filters, simple aggregates |
| Medium | 20 | Two- to four-table joins, GROUP BY, date filtering |
| Hard | 15 | Five-table joins, subqueries, CTEs, window functions, relational division |
| Business | 10 | Company terms the model can't know without definitions (VIP, churned, dormant, catalog utilization) |
| Refuse | 8 | Destructive requests, data that doesn't exist, predictions |

- **Database:** Pagila on PostgreSQL 18 (15 tables, 51,805 rentals, 51,061 payments).
- **Model:** Groq `openai/gpt-oss-120b`, reasoning effort `low`, temperature 0.
- **Dataset:** `evals/dataset.jsonl`. Every reference query is verified by `evals/check_dataset.py` before use.

## How scoring works
- **Execution accuracy:** a question passes when the model's SQL returns the same data as the reference SQL. Both queries are run directly against the database, with no row cap.
- **The comparison ignores** row order, column order, column names and extra columns. Numbers are rounded to 2 decimals.
- **A query the service rejects or fails to run counts as wrong.**
- **Refusal questions pass** only if the service explicitly refuses (`refused: true`).
- **Run:** `python evals/run_eval.py --label <name> --sleep 10`. Full results are saved to `evals/results/`; an interrupted run is saved with `_partial` added to its label.

## Results

| Run | Date | Core (50) | Business (10) | Refusals (8) | Avg latency | Avg tokens (prompt + completion) | What changed |
|---|---|---|---|---|---|---|---|
| baseline | 2026-11-05 | 48/50 (96%) | 2/10 (20%) | 0/8 (0%) | 691 ms | 774 + 104 | Full schema in prompt, no safety gates |
| gates | 2026-11-06 | 48/50 (96%) | 2/10 (20%) | 0/8 (0%) | not saved | not saved | sqlglot validation (6 gates) + EXPLAIN cost check |

Core breakdown for both runs: easy 15/15, medium 20/20, hard 13/15.

## Notes by run

### baseline
- **h06 (late-return percentage):** wrong answer. The model ignored "among returned rentals", so the 241 unreturned rentals were counted in the denominator. The query ran fine; it was logically wrong.
- **h13 (revenue share by rating):** SQL error. A cross-joined total was used outside `GROUP BY`. Expected to be fixed by the retry loop.
- **Business:** only standard terms passed (b03 average order value, b10 year-over-year growth). Company-specific terms all failed. Expected to be fixed by the semantic layer.
- **Refusals:** 0/8, since no refusal feature exists yet. The model sometimes declined by returning empty SQL, which is not a proper refusal.
- The business-language baseline was measured in a separate run (`baseline_business`): 2/10, 757 ms, 768 + 135 tokens.

### gates
- **No accuracy change:** every question gave the same result as the baseline, so the six validation gates and the cost check cost zero accuracy.
- **h13** now fails at the `EXPLAIN` step: Postgres caught the error while planning, before running the query.
- **Destructive requests** (r02–r04) are now blocked before reaching the database, but they still count as failed refusals until Phase 6 adds explicit refusal.
- **Test suite:** 91 tests pass, including an 18-case attack suite and a check that all 60 reference queries pass validation and stay under the cost limit.
- The run's results file wasn't saved (the script stopped after the last question). Accuracy is taken from the console output; the harness now always saves completed questions.

## Planned runs
| Run | Phase | Expected effect |
|---|---|---|
| retry | 3 | Fixes query errors the database detects (h13); can't fix logically wrong queries (h06) |
| retrieval | 4 | Fewer prompt tokens; accuracy should hold |
| semantic | 5 | Large gain on business questions |
| refusal | 6 | Refusal rate up, with no false refusals on answerable questions |


| retry | 2026-11-06 | 49/50 (98%) | 2/10 (20%) | 0/8 (0%) | 711 ms | 814 + 121 | Self-correcting retry loop (up to 3 attempts) |