# SchemaPilot Documentation

SchemaPilot generates online-safe PostgreSQL migrations from changes between two code trees. It diffs model schemas (base vs head), plans low-lock steps, and outputs forward/rollback SQL.

- Diffs models → IR (Intermediate Representation)
- Computes operations and plans safe steps per table
- Emits ordered SQL with risk flags and rollback hints

## Quick Links

- [Getting Started](../README.md)
- [CLI Reference](./cli.md)
- [Python API](./python-api.md)
- [Intermediate Representation (IR)](./ir.md)
- [Diff Operations](./diff.md)
- [Planner & SQL Generation](./planner-sqlgen.md)
- [Schema Hints](./schema-hints.md)
- [Adapters](./adapters/index.md)