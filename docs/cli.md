# CLI Reference

SchemaPilot provides a Typer-powered CLI. You can run it via the module or the installed console script.

## Commands

### Root options (backward-compatible)

If invoked without a subcommand and with required options, the root will run the diff:

```bash
python -m schema_agent.cli \
  --base-dir ./examples/before --base-module examples.before.models \
  --head-dir ./examples/after  --head-module  examples.after.models \
  --dialect postgresql \
  --out-dir ./artifacts
```

Options:
- `--base-dir` string: Base repo directory
- `--base-module` string: Dotted module path for base models (must import all models into `Base.metadata`)
- `--head-dir` string: Head repo directory
- `--head-module` string: Dotted module path for head models
- `--dialect` string: Target DB dialect (supported: `postgresql`)
- `--adapter` string: Schema adapter (`sqlalchemy` by default)
- `--out-dir` string: Output directory (default `./artifacts`)
- `--schema-hints` string: Path to `schema_hints.yml`. If omitted, looks for `./schema_hints.yml` or `<out_dir>/schema_hints.yml`
- `--fail-on-unsafe` flag: Exit non-zero if destructive operations are present and not allowlisted
- `--summary-only` flag: Print plan summary and skip writing SQL files
- `--summary-json` path: Write machine-readable summary JSON

### `run` (config-driven)

```bash
schema-agent run -c ./schema-agent.yml --out-dir ./artifacts
# or
python -m schema_agent.cli run -c ./schema-agent.yml --out-dir ./artifacts
```

Options:
- `--config, -c` path: Path to `schema-agent.yml` (default: `./schema-agent.yml`)
- `--out-dir` path: Output directory (overrides config)
- `--summary-json` path: Write machine-readable summary JSON (overrides config)

The config schema is validated; unknown keys are allowed for forward compatibility. See [Schema Hints](./schema-hints.md) and [Config](#config).

### `diff`

Explicit command equivalent to the root options. Same options as above.

## Outputs

- `forward.sql`: Ordered SQL to apply schema changes
- `rollback.sql`: Best-effort rollback script
- `ir_base.json`, `ir_head.json` (optional): IR dumps for debugging
- Console summary: Table-by-table phase counts, risk flags

## Non-transactional note

If your plan uses `CREATE INDEX CONCURRENTLY`, you may need to run the migration outside a transaction. Enable the banner via schema hints and check the generated SQL header.

## Examples

- Run with explicit flags: see above
- Run in CI on PRs: see the README GitHub Actions example