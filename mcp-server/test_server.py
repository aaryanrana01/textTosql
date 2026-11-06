from server import MAX_ROWS_FOR_ASSISTANT, describe_database, list_business_terms, shape_result
import asyncio


def test_refusal_is_passed_through():
    out = shape_result({"refused": True, "refusal_category": "modifies_data", "refusal_reason": "Read only."})
    assert out == {"status": "refused", "category": "modifies_data", "reason": "Read only."}


def test_error_keeps_stage_and_sql():
    out = shape_result({"error": "column x does not exist", "error_stage": "execution", "sql": "SELECT x"})
    assert out["status"] == "error" and out["stage"] == "execution" and out["sql"] == "SELECT x"


def test_rows_are_capped_for_the_assistant():
    rows = [[i] for i in range(MAX_ROWS_FOR_ASSISTANT + 10)]
    out = shape_result({"sql": "SELECT n", "columns": ["n"], "rows": rows, "row_count": len(rows)})
    assert len(out["rows"]) == MAX_ROWS_FOR_ASSISTANT
    assert out["truncated"] is True
    assert out["row_count"] == len(rows)  # the real total is still reported


def test_describe_database_lists_every_table():
    text = asyncio.run(describe_database())
    for table in ("film", "rental", "payment", "customer", "category"):
        assert f"- {table}:" in text


def test_business_terms_include_definitions():
    terms = {t["term"]: t for t in asyncio.run(list_business_terms())}
    assert "greater than 250" in terms["VIP customer"]["definition"]