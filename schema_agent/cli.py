from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from schema_agent.core.diff import diff_ir
from schema_agent.core.ir import IR
from schema_agent.core.sched import schedule_steps
from schema_agent.policy.hints import load_schema_hints
from schema_agent.core.registry import AdapterRegistry, DialectRegistry
from schema_agent.policy.config import load_cli_config

app = typer.Typer(add_completion=False, help="Schema Agent CLI")
console = Console()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    base_dir: Optional[str] = typer.Option(None, help="Base repo directory (legacy root usage)"),
    base_module: Optional[str] = typer.Option(None, help="Dotted module for base models"),
    head_dir: Optional[str] = typer.Option(None, help="Head repo directory"),
    head_module: Optional[str] = typer.Option(None, help="Dotted module for head models"),
    dialect: str = typer.Option("postgresql", help="Target DB dialect"),
    adapter: str = typer.Option("sqlalchemy", help=f"Schema adapter to use. Available: {', '.join(AdapterRegistry.names())}"),
    out_dir: str = typer.Option("./artifacts", help="Output directory"),
    schema_hints: Optional[str] = typer.Option(None, help="Path to schema_hints.yml"),
    fail_on_unsafe: bool = typer.Option(False, help="Fail on destructive ops not allowlisted"),
    summary_only: bool = typer.Option(False, help="Print plan only, skip writing SQL files"),
    summary_json: Optional[str] = typer.Option(None, help="If set, write plan summary JSON to this file"),
):
    """Backward-compatible root options: if provided without a subcommand, run the diff command."""
    if ctx.invoked_subcommand is None and base_dir and head_dir:
        return diff(
            base_dir=base_dir,
            base_module=base_module,
            head_dir=head_dir,
            head_module=head_module,
            dialect=dialect,
            adapter=adapter,
            out_dir=out_dir,
            schema_hints=schema_hints,
            fail_on_unsafe=fail_on_unsafe,
            summary_only=summary_only,
            summary_json=summary_json,
        )
    # If a subcommand is invoked, do nothing here
    return None


@app.command("run")
def run(
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to schema-agent.yml config"),
    out_dir: str = typer.Option("./artifacts", help="Output directory (overrides config)"),
    summary_json: Optional[str] = typer.Option(None, help="If set, write plan summary JSON to this file"),
):
    """Run using a YAML config file. Looks for ./schema-agent.yml if not provided."""
    cfg_path = config or os.path.join(os.getcwd(), "schema-agent.yml")
    cfg = load_cli_config(cfg_path)
    if not cfg:
        raise typer.BadParameter(f"Config not found or invalid at {cfg_path}")

    adapter = cfg.get("adapter", "sqlalchemy")
    dialect = cfg.get("dialect", "postgresql")
    base_dir = cfg.get("base_dir")
    head_dir = cfg.get("head_dir")
    base_module = cfg.get("base_module")
    head_module = cfg.get("head_module")
    schema_hints = cfg.get("schema_hints")

    return diff(
        base_dir=base_dir,
        base_module=base_module,
        head_dir=head_dir,
        head_module=head_module,
        dialect=dialect,
        adapter=adapter,
        out_dir=out_dir,
        schema_hints=schema_hints,
        fail_on_unsafe=bool(cfg.get("fail_on_unsafe", False)),
        summary_only=bool(cfg.get("summary_only", False)),
        summary_json=summary_json or cfg.get("summary_json"),
    )


@app.command("diff")
def diff(
    base_dir: str = typer.Option(..., help="Base repo directory"),
    base_module: Optional[str] = typer.Option(None, help="Dotted module for base models"),
    head_dir: str = typer.Option(..., help="Head repo directory"),
    head_module: Optional[str] = typer.Option(None, help="Dotted module for head models"),
    dialect: str = typer.Option("postgresql", help="Target DB dialect"),
    adapter: str = typer.Option("sqlalchemy", help=f"Schema adapter to use. Available: {', '.join(AdapterRegistry.names())}"),
    out_dir: str = typer.Option("./artifacts", help="Output directory"),
    schema_hints: Optional[str] = typer.Option(None, help="Path to schema_hints.yml. If not provided, will look for './schema_hints.yml' or '{out_dir}/schema_hints.yml'"),
    fail_on_unsafe: bool = typer.Option(False, help="Fail on destructive ops not allowlisted"),
    summary_only: bool = typer.Option(False, help="Print plan only, skip writing SQL files"),
    summary_json: Optional[str] = typer.Option(None, help="If set, write plan summary JSON to this file"),
):
    # Validate adapter
    adapter_factory = AdapterRegistry.get(adapter)
    if not adapter_factory:
        raise typer.BadParameter(f"Unknown adapter '{adapter}'. Available: {', '.join(AdapterRegistry.names())}")

    # Validate dialect
    planner = DialectRegistry.get_planner(dialect)
    sqlgen = DialectRegistry.get_sqlgen(dialect)
    if not planner or not sqlgen:
        raise typer.BadParameter(
            f"Unsupported dialect '{dialect}'. Supported: {', '.join(DialectRegistry.supported_dialects())}"
        )

    # resolve hints path with defaults
    hints_path = schema_hints
    if not hints_path:
        for candidate in [os.path.join(os.getcwd(), "schema_hints.yml"), os.path.join(out_dir, "schema_hints.yml")]:
            if os.path.exists(candidate):
                hints_path = candidate
                break
    hints = load_schema_hints(hints_path)

    adapter_impl = adapter_factory()
    base_ir: IR = adapter_impl.emit_ir(repo_path=base_dir, module_hint=base_module)
    head_ir: IR = adapter_impl.emit_ir(repo_path=head_dir, module_hint=head_module)

    # Debug when no tables detected
    if not base_ir.tables or not head_ir.tables:
        console.print("[yellow]No tables detected in one of the trees. base tables=%s head tables=%s[/yellow]" % (list(base_ir.tables.keys()), list(head_ir.tables.keys())))

    ops = diff_ir(base_ir, head_ir, hints)
    steps = planner(base_ir, head_ir, ops, hints)
    ordered = schedule_steps(steps)

    forward_sql, rollback_sql, summary = sqlgen(ordered, hints)
    # If nothing was generated, be explicit
    if len(ordered) == 0:
        forward_sql = "-- no schema changes detected\n"
        rollback_sql = "-- no schema changes detected\n"

    _print_summary(summary)
    if summary_json:
        Path(summary_json).write_text(json.dumps(summary, indent=2))

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


