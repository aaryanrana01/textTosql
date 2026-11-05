from app.schema_text import CATALOG, HIDDEN_COLUMNS


def test_every_documented_table_and_column_exists():
    for table, doc in CATALOG.docs.items():
        assert table in CATALOG.schema, f"schema_docs.yaml describes unknown table {table}"
        known = {c["name"] for c in CATALOG.schema[table]["columns"]}
        for column in (doc or {}).get("columns") or {}:
            assert column in known, f"schema_docs.yaml describes unknown column {table}.{column}"


def test_every_table_has_a_description():
    missing = [t for t in CATALOG.table_names if not (CATALOG.docs.get(t) or {}).get("description")]
    assert not missing, f"tables without a description: {missing}"


def test_join_path_expansion_adds_bridge_tables():
    tables = CATALOG.connect(["payment", "category"])
    assert {"rental", "inventory", "film_category"} <= tables


def test_junction_tables_bring_both_ends():
    assert {"film", "category"} <= CATALOG.connect(["film_category"])
    assert {"film", "actor"} <= CATALOG.connect(["film_actor"])
    assert not CATALOG._is_junction("rental")


def test_payment_has_foreign_keys():
    # Regression test: payment is partitioned, and its foreign keys were once lost by the schema dump.
    refs = {fk["ref_table"] for fk in CATALOG.schema["payment"]["foreign_keys"]}
    assert {"customer", "rental", "staff"} <= refs


def test_hidden_columns_are_not_rendered():
    text = CATALOG.render(CATALOG.table_names)
    for column in HIDDEN_COLUMNS:
        assert f"  {column} " not in text


def test_credentials_are_not_in_the_schema():
    staff_columns = {c["name"] for c in CATALOG.schema["staff"]["columns"]}
    assert not {"password", "username"} & staff_columns