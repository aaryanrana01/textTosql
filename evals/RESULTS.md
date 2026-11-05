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
| retry | 2026-11-06 | 49/50 (98%) | 2/10 (20%) | 0/8 (0%) | 711 ms | 814 + 121 | Self-correcting retry loop (up to 3 attempts) |
| retrieval | pending | | | | | | Table descriptions + pgvector schema retrieval (k=4) |

Core breakdown: baseline and gates, easy 15/15, medium 20/20, hard 13/15. Retry: easy 15/15, medium 20/20, hard 14/15.

## Schema retrieval recall
Measured with `evals/retrieval_recall.py` (no LLM tokens): for each answerable question, does retrieval (top-k tables plus join-path expansion) include every table the reference SQL uses?

| Change | Recall at k=4 | Avg tables per prompt |
|---|---|---|
| First version | 53/60 (88%) | 4.7 |
| Fixed missing foreign keys on partitioned `payment` table | 55/60 (92%) | 4.8 |
| Clearer, general table descriptions | 57/60 (95%) | 4.9 |
| Junction tables bring both connected tables | 59/60 (98%) | 5.2 |
| Business-term tables from the semantic layer (Phase 5) | 60/60 (100%) | 5.2 |

- **Remaining miss:** none. b07 is now covered by the ‘best performer’ definition.
- **Prompt size:** the full schema with descriptions is ~1,133 tokens; a typical retrieved schema is ~628 (about 45% less). Example: the top-5-categories-by-revenue question received 6 tables (`category`, `film`, `film_category`, `inventory`, `payment`, `rental`) and 798 prompt tokens in total, including rules.
- **k=4 was chosen** because higher values add tables without finding any more of the needed ones.

## Notes by run

### baseline
- **h06 (late-return percentage):** wrong answer. The model ignored "among returned rentals", so the 241 unreturned rentals were counted in the denominator. The query ran fine; it was logically wrong.
- **h13 (revenue share by rating):** SQL error. A cross-joined total was used outside `GROUP BY`.
- **Business:** only standard terms passed (b03 average order value, b10 year-over-year growth). Company-specific terms all failed.
- **Refusals:** 0/8, since no refusal feature exists yet. The model sometimes declined by returning empty SQL, which is not a proper refusal.
- The business-language baseline was measured in a separate run (`baseline_business`): 2/10, 757 ms, 768 + 135 tokens.

### gates
- **No accuracy change:** every question gave the same result as the baseline, so the six validation gates and the cost check cost zero accuracy.
- **h13** now fails at the `EXPLAIN` step: Postgres caught the error while planning, before running the query.
- **Destructive requests** (r02–r04) are now blocked before reaching the database, but still count as failed refusals until Phase 6 adds explicit refusal.
- **Test suite:** 91 tests at this point, including an 18-case attack suite and a check that all 60 reference queries pass validation and stay under the cost limit.
- The run's results file wasn't saved (the script stopped after the last question). Accuracy is taken from the console output; the harness now always saves completed questions.

### retry
- **h13 fixed:** the first attempt failed with the `GROUP BY` error; the model read the error and rewrote the query with a window function (`SUM(SUM(amount)) OVER ()`). Correct on the second attempt.
- **h06 still wrong:** the query runs without error, so there's nothing for the retry loop to react to. Retries fix detectable errors, not wrong logic.
- **Cost of retries:** average prompt tokens rose from 774 to 814, and a retried question costs roughly double (h13: 2,084 tokens, 1.7 s).
- Every request is now recorded in `app.request_log`.

### retrieval (accuracy run pending)
- **Security addition:** `staff.password` and `staff.username` are no longer readable by the `reader` role (column-level grants), and so no longer appear in `schema.json` or any prompt.
- **Bug found and fixed:** `payment` is a partitioned table whose foreign keys were defined on the monthly partitions, and the schema dump only read the parent. Every earlier run therefore showed `payment` without join information; the model had been guessing those joins from column names. Fixed by reading constraints from partitions too (`pg_inherits`), with a regression test.

## Planned runs
| Run | Phase | Expected effect |
|---|---|---|
| retrieval | 4 | Accuracy should hold with a smaller schema in the prompt |
| semantic | 5 | Large gain on business questions |
| refusal | 6 | Refusal rate up, with no false refusals on answerable questions |