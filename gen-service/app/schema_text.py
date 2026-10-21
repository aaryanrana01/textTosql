import json
from pathlib import Path


def load_schema_text(path: Path) -> str:
    schema = json.loads(path.read_text())
    lines = []
    for table, info in schema.items():
        fks = {fk["column"]: f'{fk["ref_table"]}.{fk["ref_column"]}' for fk in info["foreign_keys"]}
        parts = []
        for col in info["columns"]:
            part = f'{col["name"]} {col["type"]}'
            if col["name"] in info["primary_key"]:
                part += " PK"
            if col["name"] in fks:
                part += f" -> {fks[col['name']]}"
            if "allowed_values" in col:
                part += " (" + ", ".join(col["allowed_values"]) + ")"
            parts.append(part)
        lines.append(f"{table}({', '.join(parts)})")
    return "\n".join(lines)