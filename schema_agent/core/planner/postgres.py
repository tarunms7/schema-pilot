from __future__ import annotations

from typing import Dict, List, Optional, Literal, Tuple
from pydantic import BaseModel, Field

from schema_agent.core.diff import Op, OpKind


class Step(BaseModel):
    id: str
    table: Optional[str]
    sql: str
    phase: Literal["prep", "backfill", "tighten", "indexes", "finalize"]
    reversible: bool = True
    depends_on: List[str] = Field(default_factory=list)
    destructive: bool = False
    reverse_sql: Optional[str] = None


def plan_postgres(base_ir, head_ir, ops: List[Op], hints: Dict) -> List[Step]:
    steps: List[Step] = []

    planner_hints = hints.get("planner", {}) or {}
    backfill_batch = int(planner_hints.get("default_backfill_batch_rows", 5000))
    use_fast_not_null: bool = bool(planner_hints.get("use_fast_not_null", False))
    use_batched_backfill: bool = bool(planner_hints.get("use_batched_backfill", False) or planner_hints.get("large_table_mode", False))
    emit_data_validation_hints: bool = bool(planner_hints.get("emit_data_validation_hints", True))

    sid = 0

    # Track per-table rename, per-column default/backfill/not-null, and validate steps
    table_rename_step: Dict[str, str] = {}
    default_step_by_col: Dict[Tuple[str, str], str] = {}
    backfill_step_by_col: Dict[Tuple[str, str], str] = {}
    notnull_step_by_col: Dict[Tuple[str, str], str] = {}
    validate_steps: List[Step] = []
    add_constraint_steps: List[Step] = []
    unsafe_allow = set(hints.get("unsafe_allow", []) or [])

    def _is_allowed(kind: str, table: Optional[str] = None, name: Optional[str] = None) -> bool:
        keys = []
        if table and name:
            keys.append(f"{kind}: {table}.{name}")
        if table and not name:
            keys.append(f"{kind}: {table}")
        if name and not table:
            keys.append(f"{kind}: {name}")
        keys.append(kind)
        return any(k in unsafe_allow for k in keys)

    def add_step(
        table: Optional[str],
        sql: str,
        phase: str,
        reversible: bool = True,
        depends_on: Optional[List[str]] = None,
        destructive: bool = False,
        reverse_sql: Optional[str] = None,
    ):
        nonlocal sid
        sid += 1
        dep_list = list(depends_on or [])
        # All steps in a table should depend on rename if present
        if table and table in table_rename_step and (not dep_list or table_rename_step[table] not in dep_list):
            dep_list.append(table_rename_step[table])
        step = Step(
            id=f"s{sid}",
            table=table,
            sql=sql,
            phase=phase,
            reversible=reversible,
            depends_on=dep_list,
            destructive=destructive,
            reverse_sql=reverse_sql,
        )
        steps.append(step)
        return step.id

    for op in ops:
        t = op.table
        k = op.kind
        p = op.payload

        if k == OpKind.RENAME_COLUMN:
            rid = add_step(t, f"ALTER TABLE {t} RENAME COLUMN {p['from']} TO {p['to']};", phase="prep")
            table_rename_step[t] = rid
            continue

        if k == OpKind.ADD_COLUMN:
            col = p["column"]
            null_sql = "" if col["nullable"] else " NULL"  # explicit NULL tolerated by PG
            col_sql = f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS {col['name']} {col['data_type']}{null_sql};"
            add_step(t, col_sql, phase="prep", reverse_sql=f"ALTER TABLE {t} DROP COLUMN IF EXISTS {col['name']};")
            # If default exists, set default BEFORE backfill to protect concurrent inserts
            if col.get("default") is not None:
                did = add_step(t, f"ALTER TABLE {t} ALTER COLUMN {col['name']} SET DEFAULT {col['default']};", phase="tighten")
                default_step_by_col[(t, col["name"])] = did
            # Backfill existing rows if column must be NOT NULL
            if not col["nullable"]:
                if use_batched_backfill:
                    bf_sql = (
                        f"-- Batched backfill\n"
                        f"DO $$\n"
                        f"DECLARE _batch INT := {backfill_batch};\n"
                        f"BEGIN\n"
                        f"  LOOP\n"
                        f"    UPDATE {t} SET {col['name']} = {col.get('default', 'NULL')}\n"
                        f"    WHERE {col['name']} IS NULL AND ctid IN (\n"
                        f"      SELECT ctid FROM {t} WHERE {col['name']} IS NULL LIMIT _batch\n"
                        f"    );\n"
                        f"    EXIT WHEN NOT FOUND;\n"
                        f"  END LOOP;\n"
                        f"END $$;"
                    )
                else:
                    bf_sql = f"UPDATE {t} SET {col['name']} = {col.get('default', 'NULL')} WHERE {col['name']} IS NULL;"
                bf_dep = []
                if (t, col["name"]) in default_step_by_col:
                    bf_dep.append(default_step_by_col[(t, col["name"])])
                bf_id = add_step(t, bf_sql, phase="backfill", reversible=False, depends_on=bf_dep)
                # Tighten
                add_step(t, f"ALTER TABLE {t} ALTER COLUMN {col['name']} SET NOT NULL;", phase="tighten", depends_on=[bf_id])
            continue

        if k == OpKind.ALTER_DEFAULT:
            default = p["default"]
            sql = f"ALTER TABLE {t} ALTER COLUMN {p['name']} " + (
                f"SET DEFAULT {default};" if default is not None else "DROP DEFAULT;"
            )
            reverse = None
            if p["default"] is not None:
                reverse = f"ALTER TABLE {t} ALTER COLUMN {p['name']} DROP DEFAULT;"
            did = add_step(t, sql, phase="tighten", reverse_sql=reverse)
            default_step_by_col[(t, p["name"])] = did
            # Ensure backfill waits for default if it exists
            bf = backfill_step_by_col.get((t, p["name"]))
            if bf:
                # mutate the existing step to depend on default
                for s in steps:
                    if s.id == bf and did not in s.depends_on:
                        s.depends_on.append(did)
                        break
            continue

        if k == OpKind.ALTER_NULLABLE:
            if p["nullable"]:
                add_step(t, f"ALTER TABLE {t} ALTER COLUMN {p['name']} DROP NOT NULL;", phase="finalize")
            else:
                # Backfill before tightening NOT NULL
                bf_dep: List[str] = []
                # If we already created default step for this column, backfill should depend on it
                did = default_step_by_col.get((t, p["name"]))
                if did:
                    bf_dep.append(did)
                # Determine backfill expression: prefer head IR default
                head_table = head_ir.tables.get(t)
                bf_expr = "<DEFAULT_OR_EXPR>"
                if head_table and p["name"] in head_table.columns:
                    d = head_table.columns[p["name"]].default
                    if d is not None:
                        bf_expr = d
                if use_batched_backfill:
                    bf_sql = (
                        f"-- Batched backfill\n"
                        f"DO $$\n"
                        f"DECLARE _batch INT := {backfill_batch};\n"
                        f"BEGIN\n"
                        f"  LOOP\n"
                        f"    UPDATE {t} SET {p['name']} = {bf_expr}\n"
                        f"    WHERE {p['name']} IS NULL AND ctid IN (\n"
                        f"      SELECT ctid FROM {t} WHERE {p['name']} IS NULL LIMIT _batch\n"
                        f"    );\n"
                        f"    EXIT WHEN NOT FOUND;\n"
                        f"  END LOOP;\n"
                        f"END $$;"
                    )
                else:
                    bf_sql = f"UPDATE {t} SET {p['name']} = {bf_expr} WHERE {p['name']} IS NULL;"
                bf_id = add_step(t, bf_sql, phase="backfill", reversible=False, depends_on=bf_dep)
                backfill_step_by_col[(t, p["name"])] = bf_id

                if use_fast_not_null:
                    # Add validated CHECK to enable fast NOT NULL
                    nn_chk_name = f"chk_{t}_{p['name']}_nn"
                    add_id = add_step(
                        t,
                        f"ALTER TABLE {t} ADD CONSTRAINT {nn_chk_name} CHECK ({p['name']} IS NOT NULL) NOT VALID;",
                        phase="prep",
                        depends_on=[bf_id],
                    )
                    v_id = add_step(
                        t,
                        f"ALTER TABLE {t} VALIDATE CONSTRAINT {nn_chk_name};",
                        phase="tighten",
                        depends_on=[add_id],
                    )
                    nn_id = add_step(
                        t,
                        f"ALTER TABLE {t} ALTER COLUMN {p['name']} SET NOT NULL;",
                        phase="tighten",
                        reverse_sql=f"ALTER TABLE {t} ALTER COLUMN {p['name']} DROP NOT NULL;",
                        depends_on=[v_id],
                    )
                    # Drop the helper check
                    add_step(
                        t,
                        f"ALTER TABLE {t} DROP CONSTRAINT IF EXISTS {nn_chk_name};",
                        phase="finalize",
                        depends_on=[nn_id],
                    )
                else:
                    nn_id = add_step(
                        t,
                        f"ALTER TABLE {t} ALTER COLUMN {p['name']} SET NOT NULL;",
                        phase="tighten",
                        reverse_sql=f"ALTER TABLE {t} ALTER COLUMN {p['name']} DROP NOT NULL;",
                        depends_on=[bf_id],
                    )
                notnull_step_by_col[(t, p["name"])] = nn_id
            continue

        if k == OpKind.ALTER_COLUMN_TYPE:
            # Best-effort: use USING cast which may rewrite
            add_step(
                t,
                f"ALTER TABLE {t} ALTER COLUMN {p['name']} TYPE {p['to']} USING {p['name']}::{p['to']};",
                phase="finalize",
            )
            continue

        if k == OpKind.ADD_INDEX:
            idx = p["index"]
            cols = ", ".join(idx["columns"]) if idx.get("columns") else ""
            method = idx.get("method", "btree")
            unique = "UNIQUE " if idx.get("unique") else ""
            add_step(
                t,
                f"CREATE {unique}INDEX CONCURRENTLY IF NOT EXISTS {idx['name']} ON {t} USING {method} ({cols});",
                phase="indexes",
            )
            continue

        if k == OpKind.DROP_INDEX:
            destr = not _is_allowed("drop_index", None, p["name"])  # global index name
            add_step(t, f"DROP INDEX CONCURRENTLY IF EXISTS {p['name']};", phase="indexes", destructive=destr)
            continue

        if k == OpKind.ADD_FK:
            fk = p["fk"]
            cols = ", ".join(fk["columns"])
            rcols = ", ".join(fk["ref_columns"])
            clauses = []
            if fk.get("on_delete"):
                clauses.append(f"ON DELETE {fk['on_delete']}")
            if fk.get("on_update"):
                clauses.append(f"ON UPDATE {fk['on_update']}")
            add_id = add_step(
                t,
                f"ALTER TABLE {t} ADD CONSTRAINT {fk['name']} FOREIGN KEY ({cols}) REFERENCES {fk['ref_table']} ({rcols}) {' '.join(clauses)} NOT VALID;",
                phase="prep",
            )
            add_constraint_steps.append(next(s for s in steps if s.id == add_id))
            # Optional data hygiene hint for orphans before validate
            if emit_data_validation_hints:
                add_step(
                    t,
                    (
                        f"-- OPTIONAL: handle orphans before FK VALIDATE\n"
                        f"-- DELETE FROM {t} child WHERE NOT EXISTS (SELECT 1 FROM {fk['ref_table']} parent WHERE parent.{fk['ref_columns'][0]} = child.{fk['columns'][0]});\n"
                        f"-- or UPDATE to a fallback user_id per your rules"
                    ),
                    phase="backfill",
                    reversible=False,
                    depends_on=[add_id],
                )
            v_id = add_step(t, f"ALTER TABLE {t} VALIDATE CONSTRAINT {fk['name']};", phase="tighten", depends_on=[add_id])
            validate_steps.append(next(s for s in steps if s.id == v_id))
            continue

        if k == OpKind.DROP_FK:
            add_step(t, f"ALTER TABLE {t} DROP CONSTRAINT IF EXISTS {p['name']};", phase="finalize", destructive=True)
            continue

        if k == OpKind.ADD_CHECK:
            add_id = add_step(t, f"ALTER TABLE {t} ADD CONSTRAINT {p['name']} CHECK ({p['expr']}) NOT VALID;", phase="prep")
            add_constraint_steps.append(next(s for s in steps if s.id == add_id))
            # Optional data hygiene hint before validate
            if emit_data_validation_hints:
                add_step(
                    t,
                    (
                        f"-- OPTIONAL: ensure existing rows satisfy check before validation\n"
                        f"-- For example, if expression is {p['expr']}, you may need to clean up violating rows."
                    ),
                    phase="backfill",
                    reversible=False,
                    depends_on=[add_id],
                )
            v_id = add_step(t, f"ALTER TABLE {t} VALIDATE CONSTRAINT {p['name']};", phase="tighten", depends_on=[add_id])
            validate_steps.append(next(s for s in steps if s.id == v_id))
            continue

        if k == OpKind.DROP_CHECK:
            destr = not _is_allowed("drop_check", t, p["name"]) 
            add_step(t, f"ALTER TABLE {t} DROP CONSTRAINT IF EXISTS {p['name']};", phase="finalize", destructive=destr)
            continue

        if k == OpKind.ADD_UNIQUE:
            cols_list = p["columns"]
            # Optional: Postgres 15+ single-column NULLS NOT DISTINCT
            cols = ", ".join(cols_list) or ""
            if planner_hints.get("unique_nulls_not_distinct", False) and len(cols_list) == 1:
                cols = f"{cols} NULLS NOT DISTINCT"
            idx_name = f"uq_{t}_{'_'.join(cols_list)}_idx"
            c_name = f"uq_{t}_{'_'.join(cols_list)}"
            add_step(
                t,
                f"-- OPTIONAL: check duplicates before unique enforcement\n-- SELECT {cols}, COUNT(*) FROM {t} GROUP BY {cols} HAVING COUNT(*) > 1;",
                phase="prep",
                reversible=False,
            )
            add_step(
                t,
                f"CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS {idx_name} ON {t} ({cols});",
                phase="indexes",
            )
            # Idempotent-ish guard for attaching constraint using existing index
            guard_sql = (
                f"DO $$\nBEGIN\n"
                f"  IF NOT EXISTS (\n"
                f"    SELECT 1 FROM pg_constraint\n"
                f"    WHERE conname = '{c_name}' AND conrelid = '{t}'::regclass\n"
                f"  ) THEN\n"
                f"    ALTER TABLE {t} ADD CONSTRAINT {c_name} UNIQUE USING INDEX {idx_name} NOT DEFERRABLE;\n"
                f"  END IF;\n"
                f"END $$;"
            )
            add_step(t, guard_sql, phase="finalize")
            continue

        if k == OpKind.DROP_UNIQUE:
            destr = not _is_allowed("drop_unique", t, "_".join(p["columns"]))
            add_step(t, f"ALTER TABLE {t} DROP CONSTRAINT IF EXISTS uq_{t}_{'_'.join(p['columns'])};", phase="finalize", destructive=destr)
            continue

        if k == OpKind.CREATE_TABLE:
            # Build CREATE TABLE with columns and primary key
            tbl = p.get("table", {})
            cols = tbl.get("columns", {})
            pk = tbl.get("primary_key", []) or []

            col_defs = []
            for cname, c in cols.items():
                dtype = c.get("data_type")
                nullable = c.get("nullable", True)
                default = c.get("default")
                pieces = [cname, dtype]
                # Inline primary key if single column
                if len(pk) == 1 and pk[0] == cname:
                    pieces.append("PRIMARY KEY")
                if not nullable:
                    pieces.append("NOT NULL")
                if default is not None:
                    pieces.append(f"DEFAULT {default}")
                col_defs.append(" ".join(pieces))

            table_constraints = []
            if len(pk) > 1:
                table_constraints.append(f"PRIMARY KEY ({', '.join(pk)})")

            defs = ",\n  ".join(col_defs + table_constraints)
            create_sql = f"CREATE TABLE IF NOT EXISTS {t} (\n  {defs}\n);"
            add_step(t, create_sql, phase="prep", reversible=False, reverse_sql=f"DROP TABLE IF EXISTS {t};")

            # After creation, add checks/uniques/fks found in table payload safely
            for cname, expr in (tbl.get("checks", {}) or {}).items():
                add_id = add_step(t, f"ALTER TABLE {t} ADD CONSTRAINT {cname} CHECK ({expr}) NOT VALID;", phase="prep")
                add_step(t, f"ALTER TABLE {t} VALIDATE CONSTRAINT {cname};", phase="tighten", depends_on=[add_id])

            for uq_cols in (tbl.get("uniques", []) or []):
                cols_list = uq_cols
                cols_join = ", ".join(cols_list)
                idx_name = f"uq_{t}_{'_'.join(cols_list)}_idx"
                c_name = f"uq_{t}_{'_'.join(cols_list)}"
                add_step(t, f"CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS {idx_name} ON {t} ({cols_join});", phase="indexes")
                guard_sql = (
                    f"DO $$\nBEGIN\n"
                    f"  IF NOT EXISTS (\n"
                    f"    SELECT 1 FROM pg_constraint WHERE conname = '{c_name}' AND conrelid = '{t}'::regclass\n"
                    f"  ) THEN\n"
                    f"    ALTER TABLE {t} ADD CONSTRAINT {c_name} UNIQUE USING INDEX {idx_name} NOT DEFERRABLE;\n"
                    f"  END IF;\n"
                    f"END $$;"
                )
                add_step(t, guard_sql, phase="finalize")

            for fk_name, fk in (tbl.get("fks", {}) or {}).items():
                cols_join = ", ".join(fk.get("columns", []))
                rcols_join = ", ".join(fk.get("ref_columns", []))
                clauses = []
                if fk.get("on_delete"):
                    clauses.append(f"ON DELETE {fk['on_delete']}")
                if fk.get("on_update"):
                    clauses.append(f"ON UPDATE {fk['on_update']}")
                add_id = add_step(
                    t,
                    f"ALTER TABLE {t} ADD CONSTRAINT {fk.get('name', fk_name)} FOREIGN KEY ({cols_join}) REFERENCES {fk['ref_table']} ({rcols_join}) {' '.join(clauses)} NOT VALID;",
                    phase="prep",
                )
                add_step(t, f"ALTER TABLE {t} VALIDATE CONSTRAINT {fk.get('name', fk_name)};", phase="tighten", depends_on=[add_id])
            continue
        if k == OpKind.DROP_TABLE:
            destr = not _is_allowed("drop_table", t)
            add_step(t, f"DROP TABLE IF EXISTS {t};", phase="finalize", reversible=False, destructive=destr)
            continue

        if k == OpKind.DROP_COLUMN:
            destr = not _is_allowed("drop_column", t, p["name"]) 
            add_step(t, f"ALTER TABLE {t} DROP COLUMN IF EXISTS {p['name']};", phase="finalize", destructive=destr)
            continue

    # Ensure validate depends on NOT NULL tighten steps for the same table when present
    for vs in validate_steps:
        # Find any not-null step for this table and add as dependency
        for (tt, col), nn_id in notnull_step_by_col.items():
            if vs.table == tt and nn_id not in vs.depends_on:
                vs.depends_on.append(nn_id)

    # Ensure adding constraints (NOT VALID) happens after backfill for the table
    for cs in add_constraint_steps:
        # depend on all backfills for the same table
        for (tt, col), bf_id in backfill_step_by_col.items():
            if cs.table == tt and bf_id not in cs.depends_on:
                cs.depends_on.append(bf_id)

    return steps


