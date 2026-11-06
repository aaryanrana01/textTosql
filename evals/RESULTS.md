# Evaluation results

Every evaluation run of the text-to-SQL pipeline, what changed, and its measured effect.

## Two test sets

| Set | Questions | Purpose |
|---|---|---|
| **Development** (`evals/dataset.jsonl`) | 68: 15 easy, 20 medium, 15 hard, 10 business-language, 8 should-refuse | Measured after every phase; guided development |
| **Held-out** (`evals/holdout.jsonl`) | 20: 10 core, 6 business, 4 should-refuse | Written after development finished, frozen in a git commit before its first run, run once. Measures generalisation. |

- **Database:** Pagila on PostgreSQL 18 (15 tables, 51,805 rentals, 51,061 payments).
- **Model:** Groq `openai/gpt-oss-120b`, reasoning effort `low`, temperature 0.
- Every reference query is verified by `evals/check_dataset.py` before use.

## How scoring works
- **Execution accuracy:** a question passes when the model's SQL returns the same data as the reference SQL. Both are run directly against the database, with no row cap.
- **The comparison ignores** row order, column order, column names and extra columns. Numbers are rounded to 2 decimals.
- **A query the service rejects or fails to run counts as wrong.**
- **Refusal questions pass** only if the service explicitly refuses. **A false refusal** is an answerable question that was refused.
- **Run:** `python evals/run_eval.py --label <name> --sleep 12` (add `--dataset evals/holdout.jsonl` for the held-out set). Results are saved to `evals/results/`.

## Development set: results by phase

| Run | Phase | Core (50) | Business (10) | Refusals (8) | False refusals | Avg latency | Avg tokens (prompt + completion) | What changed |
|---|---|---|---|---|---|---|---|---|
| baseline | 1 | 48/50 (96%) | 2/10 (20%) | 0/8 | 0 | 691 ms | 774 + 104 | Full schema in prompt |
| gates | 2 | 48/50 (96%) | 2/10 (20%) | 0/8 | 0 | not saved | not saved | + 6 validation gates and a cost check |
| retry | 3 | 49/50 (98%) | 2/10 (20%) | 0/8 | 0 | 711 ms | 814 + 121 | + self-correcting retry loop |
| retrieval | 4 | pending | pending | pending | pending | pending | pending | + table descriptions, pgvector schema retrieval |
| semantic | 5 | 50/50 (100%) | 10/10 (100%) | 0/8 | 0 | 731 ms | 988 + 106 | + semantic layer (14 terms), few-shot examples |
| refusal | 6 | **50/50 (100%)** | **10/10 (100%)** | **8/8 (100%)** | **0** | 723 ms | 1,089 + 105 | + deterministic intent check and model refusal |

**What the ablation shows:**
- **The safety gates cost no accuracy:** identical results question by question.
- **The retry loop fixed a detectable SQL error** (h13), but not a logically wrong query (h06).
- **The semantic layer and examples produced the accuracy gains:** business 2/10 → 10/10, and h06 fixed, most likely by example x12, which shows the `return_date IS NOT NULL` pattern.
- **Refusal added 8/8 correct refusals with zero false refusals and zero accuracy loss.** Its cost is about 100 extra prompt tokens.
- **Overall cost of the improvements:** prompts grew about 40% (774 → 1,089 tokens) for +4 points core, +80 points business and +100 points refusal accuracy, with latency essentially unchanged.

## Held-out set (generalisation)

Written after all development, frozen before its first run (see the commit history), run once. Its results were not used to change anything.

| | Score |
|---|---|
| Core SQL (new patterns: median, top-per-group ranking, day of week, three-table anti-joins) | **10/10 (100%)** |
| Business language (unlisted phrasings, known terms in new contexts) | **3/6 (50%)** |
| Refusals (incl. a write request the intent check does not catch) | **4/4 (100%)** |
| False refusals | 1 |
| Avg latency / tokens | 1,119 ms / 1,131 + 142 |

**Failure analysis** (the score stays as measured; this explains it):

| Question | What happened | Assessment |
|---|---|---|
| hb1 "How many big-spending customers do we have?" | Refused: "big-spending" is undefined | Defensible: it didn't guess a threshold. Ideally it would ask a clarifying question. |
| hb2 "How many customers have stopped renting from us?" | Counted customers who *never* rented | **Genuine error:** a silent misinterpretation, the most serious failure type |
| hb3 "What proportion of our film catalogue was rented at least once in 2024?" | Returned 0.955 (fraction); reference 95.5 (percentage) | Correct answer on a different scale; the question's wording was ambiguous |

**Conclusion:** core SQL generation and refusal generalise fully to unseen questions. Business-term handling generalises only partly, because the glossary matches phrases, not meanings. One of the three failures is a genuine model error.

**Evidence-based next steps:**
1. Match glossary terms by meaning (embedding similarity), which would catch "stopped renting" → churned.
2. Ask a clarifying question for undefined terms instead of refusing.

Both would require a new held-out set to measure honestly.

## Schema retrieval recall
Measured with `evals/retrieval_recall.py` (no LLM tokens): for each answerable development question, does retrieval include every table the reference SQL uses?

| Change | Recall at k=4 | Avg tables per prompt |
|---|---|---|
| First version | 53/60 (88%) | 4.7 |
| Fixed missing foreign keys on partitioned `payment` table | 55/60 (92%) | 4.8 |
| Clearer, general table descriptions | 57/60 (95%) | 4.9 |
| Junction tables bring both connected tables | 59/60 (98%) | 5.2 |
| Business-term tables from the semantic layer | **60/60 (100%)** | 5.2 |

The full schema with descriptions is ~1,133 tokens; a typical retrieved schema is ~628 (about 45% less).

## Notes by run

### baseline
- **h06:** ignored "among returned rentals", so unreturned rentals were counted in the denominator. A logic error; the query ran.
- **h13:** `GROUP BY` error on a cross-joined total.
- **Business:** only standard terms passed (average order value, year-over-year growth).
- The business baseline was measured in a separate run (`baseline_business`): 2/10, 757 ms, 768 + 135 tokens.

### gates
- Identical results to the baseline, so the gates cost no accuracy. h13 now fails at the `EXPLAIN` stage, before execution.
- The run's results file wasn't saved (the script stopped after the last question); accuracy is from the console output. The harness now always saves completed questions.

### retry
- **h13 fixed:** the model read the `GROUP BY` error and rewrote the query with a window function.
- **h06 still wrong:** nothing for a retry loop to react to.
- A retried question costs roughly double (h13: 2,084 tokens, 1.7 s).

### retrieval (accuracy run pending)
- **Credential columns** (`staff.password`, `staff.username`) are made unreadable to the query role with column-level grants, so they disappear from the schema and every prompt.
- **A schema-extraction bug, found by the recall check:** the partitioned `payment` table's foreign keys were defined on its partitions and lost. Earlier runs had no join information for `payment`; the model had been guessing those joins from column names. Fixed, with a regression test.

### semantic
- **Business 10/10:** each glossary term's definition is applied exactly.
- **h06 fixed** without a dedicated change. The few-shot example x12 demonstrates the missing filter pattern.

### refusal
- **Intent check:** write requests at the start of a question are refused before any LLM call (0 tokens, ~0 ms).
- **Model refusals** cover data that doesn't exist, predictions and off-topic requests, each with a category and a reason.
- No false refusals and no accuracy change.

### holdout
- See the failure analysis above.