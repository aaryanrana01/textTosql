# Usage: source scripts/ask.sh, then: ask "your question"
ask() {
  curl -s -X POST localhost:8000/generate \
    -H "Content-Type: application/json" \
    -d "$(python -c 'import json,sys; print(json.dumps({"question": sys.argv[1]}))' "$1")" \
  | python -c '
import json, sys
r = json.load(sys.stdin)
if "detail" in r:
    print("FAILED:", r["detail"]); sys.exit()
for i, a in enumerate(r.get("attempt_history", []), 1):
    if a.get("error"):
        print("Attempt", i, "failed [" + str(a.get("stage")) + "]:", a["error"][:150])
print("SQL:", r["sql"])
print("Columns:", r["columns"])
for row in r["rows"][:10]:
    print("  ", row)
print("Rows:", r["row_count"], "| attempts:", r.get("attempts"), "| truncated:", r["truncated"],
      "| cost:", r.get("query_cost"), "| ms:", r["latency_ms"], "| tokens:", r["usage"])
if r.get("error"):
    print("ERROR [" + str(r.get("error_stage")) + "]:", r["error"])
'
}
