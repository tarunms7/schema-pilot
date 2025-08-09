from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Tuple

from pydantic import BaseModel

from schema_agent.core.ir import IR, Table


class OpKind(str, Enum):
    CREATE_TABLE = "create_table"
    DROP_TABLE = "drop_table"
    RENAME_TABLE = "rename_table"
    ADD_COLUMN = "add_column"
    DROP_COLUMN = "drop_column"
    RENAME_COLUMN = "rename_column"
    ALTER_COLUMN_TYPE = "alter_column_type"
    ALTER_NULLABLE = "alter_nullable"
    ALTER_DEFAULT = "alter_default"
    ADD_INDEX = "add_index"
    DROP_INDEX = "drop_index"
    ADD_FK = "add_fk"
    DROP_FK = "drop_fk"
    ADD_UNIQUE = "add_unique"
    DROP_UNIQUE = "drop_unique"
    ADD_CHECK = "add_check"
    DROP_CHECK = "drop_check"


class Op(BaseModel):
    kind: OpKind
    table: str
    payload: dict


def diff_ir(base: IR, head: IR, hints: Dict) -> List[Op]:
    ops: List[Op] = []

    base_tables = set(base.tables.keys())
    head_tables = set(head.tables.keys())

    for t in sorted(head_tables - base_tables):
        ops.append(Op(kind=OpKind.CREATE_TABLE, table=t, payload={"table": head.tables[t].model_dump()}))
    for t in sorted(base_tables - head_tables):
        ops.append(Op(kind=OpKind.DROP_TABLE, table=t, payload={}))

    for t in sorted(base_tables & head_tables):
        ops.extend(_diff_table(base.tables[t], head.tables[t], hints))

    return ops


def _diff_table(base: Table, head: Table, hints: Dict) -> List[Op]:
    ops: List[Op] = []

    # Columns: detect add/drop/rename/type/nullable/default
    base_cols = set(base.columns.keys())
    head_cols = set(head.columns.keys())

    removed = list(base_cols - head_cols)
    added = list(head_cols - base_cols)

    # rename hints
    hint_map: Dict[str, str] = {}
    for k, v in (hints.get("renames", {}) or {}).items():
        # format: table.col_old: table.col_new
        if ":" in k or ":" in v:
            continue
        try:
            left_t, left_c = k.split(".")
            right_t, right_c = v.split(".")
        except ValueError:
            continue
        if left_t == base.name and right_t == head.name:
            hint_map[left_c] = right_c

    # Try rename inference (simple heuristic + hints)
    renames: List[Tuple[str, str]] = []
    used_added: set[str] = set()
    for rc in removed:
        target = hint_map.get(rc)
        if target and target in added:
            renames.append((rc, target))
            used_added.add(target)
            continue
        # heuristic: match by compatible type and default
        bcol = base.columns[rc]
        for ac in added:
            if ac in used_added:
                continue
            hcol = head.columns[ac]
            if _is_type_compatible(bcol.data_type, hcol.data_type):
                renames.append((rc, ac))
                used_added.add(ac)
                break

    for old_c, new_c in renames:
        ops.append(Op(kind=OpKind.RENAME_COLUMN, table=base.name, payload={"from": old_c, "to": new_c}))

    removed = [c for c in removed if c not in {r for r, _ in renames}]
    added = [c for c in added if c not in used_added]

    for c in sorted(added):
        ops.append(Op(kind=OpKind.ADD_COLUMN, table=base.name, payload={"column": head.columns[c].model_dump()}))
    for c in sorted(removed):
        ops.append(Op(kind=OpKind.DROP_COLUMN, table=base.name, payload={"name": c}))

    # Common columns: type/default/nullable diffs
    pairs = [(c, c) for c in sorted(base_cols & head_cols)] + renames
    for src_name, dst_name in pairs:
        if src_name not in base.columns or dst_name not in head.columns:
            continue
        bcol = base.columns[src_name]
        hcol = head.columns[dst_name]
        if bcol.data_type != hcol.data_type:
            ops.append(
                Op(
                    kind=OpKind.ALTER_COLUMN_TYPE,
                    table=base.name,
                    payload={"name": dst_name, "from": bcol.data_type, "to": hcol.data_type},
                )
            )
        if bool(bcol.nullable) != bool(hcol.nullable):
            ops.append(
                Op(kind=OpKind.ALTER_NULLABLE, table=base.name, payload={"name": dst_name, "nullable": hcol.nullable})
            )
        if (bcol.default or None) != (hcol.default or None):
            ops.append(
                Op(kind=OpKind.ALTER_DEFAULT, table=base.name, payload={"name": dst_name, "default": hcol.default})
            )

    # Indexes
    base_idx = set(base.indexes.keys())
    head_idx = set(head.indexes.keys())
    for i in sorted(head_idx - base_idx):
        ops.append(Op(kind=OpKind.ADD_INDEX, table=base.name, payload={"index": head.indexes[i].model_dump()}))
    for i in sorted(base_idx - head_idx):
        ops.append(Op(kind=OpKind.DROP_INDEX, table=base.name, payload={"name": i}))

    # FKs
    base_fk = set(base.fks.keys())
    head_fk = set(head.fks.keys())
    for k in sorted(head_fk - base_fk):
        ops.append(Op(kind=OpKind.ADD_FK, table=base.name, payload={"fk": head.fks[k].model_dump()}))
    for k in sorted(base_fk - head_fk):
        ops.append(Op(kind=OpKind.DROP_FK, table=base.name, payload={"name": k}))

    # Uniques
    base_uniques = {tuple(sorted(u)) for u in base.uniques}
    head_uniques = {tuple(sorted(u)) for u in head.uniques}
    for u in sorted(head_uniques - base_uniques):
        ops.append(Op(kind=OpKind.ADD_UNIQUE, table=base.name, payload={"columns": list(u)}))
    for u in sorted(base_uniques - head_uniques):
        ops.append(Op(kind=OpKind.DROP_UNIQUE, table=base.name, payload={"columns": list(u)}))

    # Checks
    base_checks = set(base.checks.keys())
    head_checks = set(head.checks.keys())
    for k in sorted(head_checks - base_checks):
        ops.append(Op(kind=OpKind.ADD_CHECK, table=base.name, payload={"name": k, "expr": head.checks[k]}))
    for k in sorted(base_checks - head_checks):
        ops.append(Op(kind=OpKind.DROP_CHECK, table=base.name, payload={"name": k}))

    return ops


def _is_type_compatible(t1: str, t2: str) -> bool:
    if t1 == t2:
        return True
    # Simple widen/convert set for MVP
    def norm(x: str) -> str:
        return x.split("(")[0].strip().lower()

    n1, n2 = norm(t1), norm(t2)
    if {n1, n2} <= {"int", "integer", "bigint", "smallint"}:
        return True
    if n1 == n2:
        return True
    if n1 == "numeric" and n2 == "numeric":
        return True
    return False


