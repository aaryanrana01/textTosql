"""Run the evaluation set against the generation service and score it."""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "gen-service"))
from app.config import settings  # noqa: E402

SERVICE_URL = "http://localhost:8000/generate"


def connect():
    return psycopg.connect(
        host=settings.db_host, port=settings.db_port, dbname=settings.postgres_db,
        user="reader", password=settings.reader_password, autocommit=True,
    )


def normalize(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        return round(float(value), 2)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value).strip()


def run_sql(conn, sql):
    with conn.cursor() as cur:
        cur.execute(sql)
        return [[normalize(v) for v in row] for row in cur.fetchall()]


def results_match(gold, pred):
    """Every reference column must appear in the prediction with the same values.
    Row order, column order, column names and extra columns are ignored."""
    if len(gold) != len(pred):
        return False
    if not gold:
        return True
    gold_cols = [Counter(row[i] for row in gold) for i in range(len(gold[0]))]
    pred_cols = [Counter(row[i] for row in pred) for i in range(len(pred[0]))]
    used = set()
    for gold_col in gold_cols:
        match = next((j for j, p in enumerate(pred_cols) if j not in used and p == gold_col), None)
        if match is None:
            return False
        used.add(match)
    return True


def ask_service(question):
    body = json.dumps({"question": question, "use_cache": False}).encode()
    for attempt in range(2):
        req = urllib.request.Request(SERVICE_URL, data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.load(resp), None
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:200]
            if exc.code == 429 and attempt == 0:
                print("    rate limited, waiting 60 s and retrying once...")
                time.sleep(60)
                continue
            return None, f"HTTP {exc.code}: {detail}"
        except Exception as exc:
            return None, f"request failed: {exc}"
    return None, "rate limited twice"


def score(conn, item, resp, err):
    rec = {"id": item["id"], "difficulty": item["difficulty"], "expect": item["expect"], "question": item["question"]}
    if resp:
        rec.update(
            sql=resp.get("sql"),
            refused=bool(resp.get("refused")),
            latency_ms=resp.get("latency_ms"),
            usage=resp.get("usage") or {},
            error_stage=resp.get("error_stage"),
        )
    if item["expect"] == "refuse":
        rec["correct"] = bool(resp and resp.get("refused"))
        if err:
            rec["error"] = err
        return rec
    if err or not resp or resp.get("refused") or not resp.get("sql"):
        rec["correct"] = False
        rec["error"] = err or ("wrongly refused" if resp and resp.get("refused") else "no SQL returned")
        return rec
    # CHANGED (Phase 2): if the service rejected or failed to run the query, it counts as wrong.
    # Without this, the harness would run the rejected SQL itself and might score it correct.
    if resp.get("error"):
        rec["correct"] = False
        rec["error"] = f"[{resp.get('error_stage')}] {resp['error'][:180]}"
        return rec
    try:
        gold = run_sql(conn, item["gold_sql"])
        pred = run_sql(conn, resp["sql"])
        rec["correct"] = results_match(gold, pred)
        rec["gold_rows"], rec["pred_rows"] = len(gold), len(pred)
    except psycopg.Error as exc:
        rec["correct"] = False
        rec["error"] = str(exc).strip()[:200]
    return rec


def summarize(results):
    def pct(part, whole):
        return round(100 * part / whole, 1) if whole else 0.0

    answerable = [r for r in results if r["expect"] == "answer"]
    core = [r for r in answerable if r["difficulty"] in ("easy", "medium", "hard")]
    refusals = [r for r in results if r["expect"] == "refuse"]
    with_usage = [r for r in results if r.get("usage")]
    summary = {
        "accuracy": pct(sum(r["correct"] for r in answerable), len(answerable)),
        "answerable": len(answerable),
        # CHANGED (Phase 2): None instead of 0.0 when a run contains no core questions
        "core_accuracy": pct(sum(r["correct"] for r in core), len(core)) if core else None,
        "by_difficulty": {},
        "refusal_rate": pct(sum(r["correct"] for r in refusals), len(refusals)),
        "false_refusals": sum(1 for r in answerable if r.get("refused")),
        "avg_latency_ms": round(sum(r["latency_ms"] for r in with_usage) / len(with_usage)) if with_usage else None,
        "avg_prompt_tokens": round(sum(r["usage"].get("prompt_tokens", 0) for r in with_usage) / len(with_usage)) if with_usage else None,
        "avg_completion_tokens": round(sum(r["usage"].get("completion_tokens", 0) for r in with_usage) / len(with_usage)) if with_usage else None,
    }
    for level in ("easy", "medium", "hard", "business"):
        group = [r for r in answerable if r["difficulty"] == level]
        if group:
            correct = sum(r["correct"] for r in group)
            summary["by_difficulty"][level] = f"{correct}/{len(group)} ({pct(correct, len(group))}%)"
    return summary

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="run", help="name for this run, e.g. baseline")
    parser.add_argument("--dataset", default=str(ROOT / "evals" / "dataset.jsonl"), help="path to a .jsonl question set")
    parser.add_argument("--limit", type=int, help="only run the first N questions")
    parser.add_argument("--only", help="comma-separated id prefixes to run, e.g. b or h,b")
    parser.add_argument("--sleep", type=float, default=8.0, help="seconds between questions")
    parser.add_argument("--min-accuracy", type=float, help="exit with an error if answerable accuracy is below this percentage (for CI)")
    args = parser.parse_args()

    items = [json.loads(line) for line in Path(args.dataset).read_text().splitlines() if line.strip()]
    if args.only:
        prefixes = tuple(p.strip() for p in args.only.split(","))
        items = [i for i in items if i["id"].startswith(prefixes)]
    if args.limit:
        items = items[: args.limit]

    results, summary = [], None
    try:
        with connect() as conn:
            for n, item in enumerate(items, 1):
                resp, err = ask_service(item["question"])
                if err and err.startswith("HTTP 429"):
                    print(f"\nRate limit still exceeded at {item['id']}; stopping so the remaining questions aren't scored as failures.")
                    break
                rec = score(conn, item, resp, err)
                results.append(rec)
                mark = "PASS" if rec["correct"] else "FAIL"
                note = f"  ({rec['error']})" if rec.get("error") else ""
                print(f"[{n}/{len(items)}] {item['id']} {mark}  {item['question'][:70]}{note}")
                if n < len(items):
                    time.sleep(args.sleep)
    except KeyboardInterrupt:
        print("\nInterrupted: saving the questions completed so far.")
    finally:
        # Runs even if the loop crashes or is interrupted, so finished work is never lost.
        if results:
            label = args.label if len(results) == len(items) else f"{args.label}_partial"
            summary = summarize(results)
            out_dir = ROOT / "evals" / "results"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_file = out_dir / f"{datetime.now():%Y%m%d_%H%M}_{label}.json"
            out_file.write_text(json.dumps({"label": label, "summary": summary, "results": results}, indent=2, default=str))
            print("\n=== Summary ===")
            print(json.dumps(summary, indent=2))
            print(f"Saved to {out_file}")

    if args.min_accuracy is not None:
        complete = summary is not None and len(results) == len(items)
        if not complete or summary["accuracy"] < args.min_accuracy:
            got = f"{summary['accuracy']}%" if summary else "no results"
            print(f"\nAccuracy gate FAILED: required {args.min_accuracy}%, got {got} ({len(results)}/{len(items)} questions completed)")
            sys.exit(1)
        print(f"\nAccuracy gate passed: {summary['accuracy']}% >= {args.min_accuracy}%")

if __name__ == "__main__":
    main()