# Python API

This package exposes a small set of public APIs focused on:

- IR data models used internally and for debugging
- Diffing IR into operations
- Planning steps and generating SQL per dialect
- Adapter and dialect registries
- CLI entrypoint (`schema_agent.cli:app`)

## Top-level exports

From `schema_agent.__init__`:

- `__version__`: Package version
- `AdapterRegistry`: Register/get schema adapters
- `DialectRegistry`: Register/get planners and SQL generators

Example:

```python
from schema_agent import AdapterRegistry, DialectRegistry

# List adapters
print(AdapterRegistry.names())  # ("sqlalchemy",)

# Resolve Postgres planner & sqlgen
planner = DialectRegistry.get_planner("postgresql")
sqlgen = DialectRegistry.get_sqlgen("postgresql")
```

## Registries

```python
from schema_agent.core.registry import AdapterRegistry, DialectRegistry
```

- `AdapterRegistry.register(name: str, factory: Callable[[], object]) -> None`
- `AdapterRegistry.get(name: str) -> Optional[Callable[[], object]]`
- `AdapterRegistry.names() -> Tuple[str, ...]`

- `DialectRegistry.register_planner(dialect: str, planner: Callable) -> None`
- `DialectRegistry.register_sqlgen(dialect: str, sqlgen: Callable) -> None`
- `DialectRegistry.get_planner(dialect: str) -> Optional[Callable]`
- `DialectRegistry.get_sqlgen(dialect: str) -> Optional[Callable]`
- `DialectRegistry.supported_dialects() -> Tuple[str, ...]`

## IR Models

See [IR](./ir.md) for full details.

```python
from schema_agent.core.ir import IR, Table, Column, Index, ForeignKey
```

## Diff → Plan → SQL

Low-level building blocks if you want to call the engine in-process.

```python
from schema_agent.adapters.sqlalchemy.adapter import SQLAlchemyAdapter
from schema_agent.core.diff import diff_ir
from schema_agent.core.sched import schedule_steps
from schema_agent.core.registry import DialectRegistry

# 1) Build IRs from two trees
adapter = SQLAlchemyAdapter()
base_ir = adapter.emit_ir(repo_path="./examples/before", module_hint="examples.before.models")
head_ir = adapter.emit_ir(repo_path="./examples/after", module_hint="examples.after.models")

# 2) Load optional hints
from schema_agent.policy.hints import load_schema_hints
hints = load_schema_hints("./schema_hints.yml")

# 3) Diff and plan
ops = diff_ir(base_ir, head_ir, hints)
planner = DialectRegistry.get_planner("postgresql")
steps = planner(base_ir, head_ir, ops, hints)
ordered = schedule_steps(steps)

# 4) Generate SQL and summary
sqlgen = DialectRegistry.get_sqlgen("postgresql")
forward_sql, rollback_sql, summary = sqlgen(ordered, hints)
print(forward_sql)
print(rollback_sql)
print(summary)
```

## CLI Config and Schema Hints

- `schema_agent.policy.config.load_cli_config(path) -> dict`: Load and validate YAML config
- `schema_agent.policy.hints.load_schema_hints(path) -> dict`: Load optional hints

See: [Schema Hints](./schema-hints.md).