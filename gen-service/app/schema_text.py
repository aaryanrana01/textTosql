"""Schema catalog: structure from db/schema.json plus human-written descriptions from db/schema_docs.yaml."""
import json
from collections import deque
from pathlib import Path

import yaml

from .config import ROOT

# Bookkeeping columns that never answer business questions; hiding them saves prompt tokens.
HIDDEN_COLUMNS = {"last_update", "uuid"}


class SchemaCatalog:
    def __init__(self, schema_path: Path, docs_path: Path):
        self.schema = json.loads(schema_path.read_text())
        self.docs = yaml.safe_load(docs_path.read_text())["tables"]
        self.table_names = sorted(self.schema)

        # Undirected graph of foreign-key links, used to find join paths between tables.
        self.graph: dict[str, set[str]] = {name: set() for name in self.schema}
        for name, info in self.schema.items():
            for fk in info["foreign_keys"]:
                if fk["ref_table"] in self.graph:
                    self.graph[name].add(fk["ref_table"])
                    self.graph[fk["ref_table"]].add(name)

    def _column_docs(self, table: str) -> dict:
        return (self.docs.get(table) or {}).get("columns") or {}

    def _visible_columns(self, table: str):
        return [c for c in self.schema[table]["columns"] if c["name"] not in HIDDEN_COLUMNS]

    def table_text(self, table: str) -> str:
        """One table as prompt text: description, then one line per column."""
        info = self.schema[table]
        docs = self._column_docs(table)
        fks = {fk["column"]: f'{fk["ref_table"]}.{fk["ref_column"]}' for fk in info["foreign_keys"]}
        lines = [f"{table}: {(self.docs.get(table) or {}).get('description', '')}"]
        for col in self._visible_columns(table):
            line = f'  {col["name"]} {col["type"]}'
            if col["name"] in info["primary_key"]:
                line += " PK"
            if col["name"] in fks:
                line += f" -> {fks[col['name']]}"
            if "allowed_values" in col:
                line += " (" + ", ".join(col["allowed_values"]) + ")"
            if col["name"] in docs:
                line += f" -- {docs[col['name']]}"
            lines.append(line)
        return "\n".join(lines)

    def render(self, tables) -> str:
        return "\n\n".join(self.table_text(t) for t in sorted(tables))

    def document(self, table: str) -> str:
        """Text embedded for retrieval: the table's meaning in plain words."""
        docs = self._column_docs(table)
        parts = [f"{c['name']} ({docs[c['name']]})" if c["name"] in docs else c["name"] for c in self._visible_columns(table)]
        description = (self.docs.get(table) or {}).get("description", "")
        return f"Table {table}: {description} Columns: {', '.join(parts)}."

    def _shortest_path(self, start: str, goal: str) -> list[str]:
        previous = {start: None}
        queue = deque([start])
        while queue:
            node = queue.popleft()
            if node == goal:
                break
            for neighbour in sorted(self.graph[node]):
                if neighbour not in previous:
                    previous[neighbour] = node
                    queue.append(neighbour)
        if goal not in previous:
            return []
        path, node = [], goal
        while node is not None:
            path.append(node)
            node = previous[node]
        return path

    def _is_junction(self, table: str) -> bool:
        """A link table whose only real columns are foreign keys, e.g. film_category or film_actor."""
        fk_columns = {fk["column"] for fk in self.schema[table]["foreign_keys"]}
        visible = {c["name"] for c in self._visible_columns(table)}
        return len(fk_columns) >= 2 and visible <= fk_columns


    def connect(self, tables) -> set[str]:
        """Add the tables needed to join the selected ones:
        1. both ends of any selected junction table, which is meaningless without them;
        2. bridge tables along the shortest foreign-key path between every pair."""
        selected = [t for t in dict.fromkeys(tables) if t in self.graph]
        for table in list(selected):
            if self._is_junction(table):
                for fk in self.schema[table]["foreign_keys"]:
                    if fk["ref_table"] not in selected:
                        selected.append(fk["ref_table"])
        result = set(selected)
        for i, a in enumerate(selected):
            for b in selected[i + 1:]:
                result.update(self._shortest_path(a, b))
        return result


CATALOG = SchemaCatalog(ROOT / "db" / "schema.json", ROOT / "db" / "schema_docs.yaml")