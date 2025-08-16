# Schema Hints & Config

Schema hints let you tune planning behavior, allowlist destructive operations, and derive environment-specific options.

Hints are loaded from YAML via `schema_agent.policy.hints.load_schema_hints(path)`.

## File discovery

- CLI tries `--schema-hints PATH`
- If omitted, it looks for `./schema_hints.yml` or `<out_dir>/schema_hints.yml`

## Structure (examples)

```yaml
# Unsafe allowlist: explicitly allow some destructive operations
unsafe_allow:
  # allow dropping a specific column
  - "drop_column: users.legacy_flag"
  # allow dropping a specific unique constraint
  - "drop_unique: users.email"
  # allow dropping a global index by name
  - "drop_index: idx_old_global"
  # allow dropping a specific table
  - "drop_table: temp_processing"

# Planner tuning
planner:
  default_backfill_batch_rows: 5000
  use_batched_backfill: true
  use_fast_not_null: true
  emit_data_validation_hints: true
  add_banner_for_non_txn: true
  unique_nulls_not_distinct: false

# Rename hints (help detect renames rather than drop+add)
renames:
  # table column old → new
  users.name_full: users.full_name

# Dialect specific
Dialect:
  postgres:
    target_version: "15"
```

Notes:
- The allowlist is matched against several key forms, in order of specificity: `"kind: table.name"`, `"kind: table"`, `"kind: name"`, `"kind"`.
- When `target_version` is set, a derived value `_derived.pg_major` is added for convenience.

## Config file

The `run` command reads `schema-agent.yml` using `schema_agent.policy.config.load_cli_config(path)` and validates it with a Pydantic schema (unknown keys allowed).

Required keys:
- `base_dir`, `head_dir`

Optional keys:
- `adapter` (default `sqlalchemy`)
- `dialect` (default `postgresql`)
- `base_module`, `head_module`
- `schema_hints`
- `fail_on_unsafe` (bool)
- `summary_only` (bool)
- `summary_json` (path)

Example:

```yaml
adapter: sqlalchemy
dialect: postgresql
base_dir: ./examples/before
base_module: examples.before.models
head_dir: ./examples/after
head_module: examples.after.models
schema_hints: ./schema_hints.yml
fail_on_unsafe: false
summary_only: false
summary_json: artifacts/summary.json
```