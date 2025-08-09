from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Tuple

from schema_agent.core.planner.postgres import Step


def generate_postgres_sql(steps: List[Step], hints: Dict | None = None) -> Tuple[str, str, Dict]:
    # Group by table and concatenate respecting given order
    forward_lines: List[str] = []
    rollback_lines: List[str] = []

    table_to_steps: Dict[str, List[Step]] = defaultdict(list)
    for s in steps:
        table_to_steps[s.table or "__global__"].append(s)

    # Summary info
    summary: Dict = {"tables": {}, "unsafe": False}

    for table, tsteps in table_to_steps.items():
        forward_lines.append(f"-- ==== Table: {table} ====")
        for s in tsteps:
            if s.destructive:
                forward_lines.append("-- DESTRUCTIVE (commented out by default):")
                for line in s.sql.splitlines():
                    forward_lines.append(f"-- {line}")
            else:
                forward_lines.append(s.sql)

        # rollback: reverse order for table-specific steps
        rollback_lines.append(f"-- ==== Table: {table} (rollback) ====")
        for s in reversed(tsteps):
            if s.reverse_sql:
                rollback_lines.append(s.reverse_sql)
            else:
                if s.reversible:
                    rollback_lines.append(f"-- rollback for step {s.id} may be lossy")
                rollback_lines.append(f"-- forward: {s.sql}")

        # Build summary table stats
        phase_counts = [0, 0, 0, 0, 0]
        idx = {"prep": 0, "backfill": 1, "tighten": 2, "indexes": 3, "finalize": 4}
        risks: List[str] = []
        ops_here = []
        for s in tsteps:
            phase_counts[idx[s.phase]] += 1
            # risk flags heuristics
            if "NOT VALID" in s.sql:
                risks.append("fk_validate")
            if "CREATE" in s.sql and "INDEX CONCURRENTLY" in s.sql:
                risks.append("concurrent_index")
            if "SET NOT NULL" in s.sql:
                risks.append("not_null_tighten")
            if "USING" in s.sql and "ALTER COLUMN" in s.sql and "TYPE" in s.sql:
                risks.append("rewrite_likely")
            if s.destructive:
                risks.append("destructive_present")
                summary["unsafe"] = True
            ops_here.append(s.phase)

        summary["tables"][table] = {
            "ops": sorted(set(ops_here)),
            "risks": sorted(set(risks)),
            "phase_counts": phase_counts,
        }

    forward_sql = "\n".join(forward_lines) + "\n"
    rollback_sql = "\n".join(rollback_lines) + "\n"

    # Add non-transactional banner if requested and concurrent indexes are present
    add_banner = bool((hints or {}).get("planner", {}).get("add_banner_for_non_txn", False))
    if add_banner and "INDEX CONCURRENTLY" in forward_sql:
        banner = "-- NOTE: This migration must run OUTSIDE a transaction due to CONCURRENTLY.\n\n"
        forward_sql = banner + forward_sql

    return forward_sql, rollback_sql, summary


