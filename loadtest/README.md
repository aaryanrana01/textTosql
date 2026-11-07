# Load test

Measures how fast QueryWise answers, and how much traffic it handles, using [k6](https://k6.io).

## What is tested
The exact production container (`Dockerfile`), with fixed resources: **1 CPU and 512 MB memory** (the free hosting tier's memory limit).
Two scenarios run one after the other, each for 60 seconds at a constant rate:

| Scenario | Path exercised | LLM tokens |
|---|---|---|
| **Refusals** ("Delete all rentals.") | Express (auth, validation, rate limits, history) → generation service → intent check → request log | 0 |
| **Cached answers** (a question answered once beforehand) | All of the above, plus the cache lookup, all six safety gates, the `EXPLAIN` cost check and running the SQL on PostgreSQL | 0 (one LLM call to fill the cache) |

Every response is checked for correctness (really refused, really served from the cache), not just speed.
Fresh LLM answers are not load-tested: their time is mostly the LLM provider's, and it is measured by the evaluation runs instead (about 720 ms on average; see `evals/RESULTS.md`).

## Results (1 CPU, 512 MB)

| Rate (per scenario) | Refusals p50 / p95 | Cached answers p50 / p95 | Errors | Peak memory |
|---|---|---|---|---|
| **5 req/s** | **7 ms / 13 ms** | **108 ms / 172 ms** | **0** | ~485 MiB |
| 10 req/s | 10 ms / 23 ms | 4.5 s / 7.0 s | 0 | ~489 MiB |

- **At 5 req/s, all targets pass** (p95 under 500 ms for refusals and under 1 s for cached answers; fewer than 1% errors).
- **At 10 req/s, cached answers exceed what one CPU can serve,** so requests queue and latency rises. There were still no errors. **Capacity on 1 CPU is between 5 and about 9 cached answers per second.**
- **Memory peaks at about 485 MiB of 512 MiB under load,** the main constraint if traffic grew.
- **The live demo runs on a smaller free instance (a fraction of one CPU),** so it is sized for demo traffic; these figures describe the container on 1 CPU, not the live site.

## How to run it
```bash
docker compose up -d                       # local database and Redis
docker build -t querywise .
docker run --rm --name querywise-test --network host --cpus=1 --memory=512m \
  --env-file .env -e PORT=4100 -e DB_SSLMODE=prefer -e DB_SSL=false \
  -e QUERY_RATE_LIMIT_PER_HOUR=100000 -e DAILY_TOKEN_BUDGET=100000 \
  -e LANGFUSE_PUBLIC_KEY= -e LANGFUSE_SECRET_KEY= querywise

# in another terminal (RATE = requests per second per scenario; default 10)
docker run --rm -i --network host -e RATE=5 -v "$PWD/loadtest:/scripts" grafana/k6 run /scripts/k6.js
```
The rate limit is raised only for the test (one guest sends ~600–1,200 requests), and tracing is turned off so test traffic doesn't fill the tracing dashboard.