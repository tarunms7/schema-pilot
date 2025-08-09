from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from schema_agent.adapters.sqlalchemy.adapter import SQLAlchemyAdapter
from schema_agent.core.diff import diff_ir
from schema_agent.core.ir import IR
from schema_agent.core.planner.postgres import plan_postgres
from schema_agent.core.sched import schedule_steps
from schema_agent.core.sqlgen.postgres import generate_postgres_sql
from schema_agent.policy.hints import load_schema_hints


app = typer.Typer(add_completion=False, help="Schema Agent CLI")
console = Console()


@app.command("diff")
def diff(
    base_dir: str = typer.Option(..., help="Base repo directory"),
    base_module: Optional[str] = typer.Option(None, help="Dotted module for base models"),
    head_dir: str = typer.Option(..., help="Head repo directory"),
    head_module: Optional[str] = typer.Option(None, help="Dotted module for head models"),
    dialect: str = typer.Option("postgresql", help="Target DB dialect"),
    out_dir: str = typer.Option("./artifacts", help="Output directory"),
    schema_hints: Optional[str] = typer.Option(None, help="Path to schema_hints.yml"),
    fail_on_unsafe: bool = typer.Option(False, help="Fail on destructive ops not allowlisted"),
    summary_only: bool = typer.Option(False, help="Print plan only, skip writing SQL files"),
):
    if dialect != "postgresql":
        raise typer.BadParameter("MVP supports only postgresql")

    hints = load_schema_hints(schema_hints)

    adapter = SQLAlchemyAdapter()
    base_ir: IR = adapter.emit_ir(repo_path=base_dir, module_hint=base_module)
    head_ir: IR = adapter.emit_ir(repo_path=head_dir, module_hint=head_module)

    # Debug when no tables detected
    if not base_ir.tables or not head_ir.tables:
        console.print("[yellow]No tables detected in one of the trees. base tables=%s head tables=%s[/yellow]" % (list(base_ir.tables.keys()), list(head_ir.tables.keys())))

    ops = diff_ir(base_ir, head_ir, hints)
    steps = plan_postgres(base_ir, head_ir, ops, hints)
    ordered = schedule_steps(steps)

    forward_sql, rollback_sql, summary = generate_postgres_sql(ordered, hints)
    # If nothing was generated, be explicit
    if len(ordered) == 0:
        forward_sql = "-- no schema changes detected\n"
        rollback_sql = "-- no schema changes detected\n"

    _print_summary(summary)

    if not summary_only:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        (Path(out_dir) / "forward.sql").write_text(forward_sql)
        (Path(out_dir) / "rollback.sql").write_text(rollback_sql)
        # Debug: dump IRs for troubleshooting in CI
        try:
            (Path(out_dir) / "ir_base.json").write_text(base_ir.model_dump_json(indent=2))
            (Path(out_dir) / "ir_head.json").write_text(head_ir.model_dump_json(indent=2))
        except Exception:
            pass

    # Optionally enforce fail_on_unsafe if planner flagged dangerous ops
    if fail_on_unsafe and summary.get("unsafe", False):
        raise typer.Exit(code=2)


def _print_summary(summary: dict) -> None:
    table = Table(title="Schema Agent Plan Summary")
    table.add_column("Table")
    table.add_column("Ops")
    table.add_column("Risk Flags")
    table.add_column("Steps (prep/backfill/tighten/indexes/finalize)")

    for tname, info in summary.get("tables", {}).items():
        table.add_row(
            tname,
            ", ".join(info.get("ops", [])),
            ", ".join(info.get("risks", [])),
            "/".join(str(x) for x in info.get("phase_counts", [0, 0, 0, 0, 0])),
        )
    console.print(table)


if __name__ == "__main__":
    app()


