# Planner & SQL Generation

SchemaPilot plans low-lock, online-safe steps for each table and generates forward/rollback SQL.

## Step Model

```python
from schema_agent.core.planner.postgres import Step
```

- `id: str` stable step identifier
- `table: Optional[str]`
- `sql: str` forward SQL
- `phase: Literal["prep", "backfill", "tighten", "indexes", "finalize"]`
- `reversible: bool = True`
- `depends_on: List[str] = []`
- `destructive: bool = False` (destructive steps are commented out by default in forward SQL)
- `reverse_sql: Optional[str]`

## Planning (PostgreSQL)

```python
from schema_agent.core.registry import DialectRegistry
steps = DialectRegistry.get_planner("postgresql")(base_ir, head_ir, ops, hints)
```

Highlights:
- Adds columns with defaults before backfill to protect concurrent inserts
- Uses NOT VALID constraints and VALIDATE to avoid long locks
- Supports optional batched backfill and fast NOT NULL with helper CHECK
- Creates indexes CONCURRENTLY
- Marks destructive operations; can be blocked unless allowlisted in hints

## Scheduling

```python
from schema_agent.core.sched import schedule_steps
ordered = schedule_steps(steps)
```

Performs a topological sort on `depends_on` to order steps.

## SQL Generation

```python
from schema_agent.core.registry import DialectRegistry
forward_sql, rollback_sql, summary = DialectRegistry.get_sqlgen("postgresql")(ordered, hints)
```

Behavior:
- Groups steps by table; forwards in order, rollbacks in reverse
- Comments out destructive steps in forward output
- Emits a per-table summary with phase counts and risk flags
- Optionally adds a header banner if non-transactional operations are present and configured

### Summary structure

```python
{
  "tables": {
    "users": {
      "ops": ["prep", "backfill", ...],
      "risks": ["not_null_tighten", "concurrent_index", ...],
      "phase_counts": [prep, backfill, tighten, indexes, finalize]
    }
  },
  "unsafe": true | false
}
```

## End-to-end example

See [Python API](./python-api.md#diff-→-plan-→-sql) for a complete example.