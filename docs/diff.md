# Diff Operations

The diff engine compares two IR trees and produces a sequence of operations (`Op`) describing schema changes.

## API

```python
def diff_ir(base: IR, head: IR, hints: Dict) -> List[Op]
```

- `base`: IR from the base tree
- `head`: IR from the head tree
- `hints`: schema hints; supports optional column rename hints and more

Returns a list of `Op`:

```python
from schema_agent.core.diff import Op, OpKind

class Op(BaseModel):
    kind: OpKind
    table: str
    payload: dict
```

## Operation kinds

- `CREATE_TABLE`: create a table described by `payload["table"]`
- `DROP_TABLE`: drop table
- `RENAME_TABLE` (reserved): not currently emitted by the default diff
- `ADD_COLUMN`: `payload["column"]` contains column descriptor
- `DROP_COLUMN`: `payload["name"]`
- `RENAME_COLUMN`: `payload = {"from": old, "to": new}`
- `ALTER_COLUMN_TYPE`: `payload = {"name": col, "from": type, "to": type}`
- `ALTER_NULLABLE`: `payload = {"name": col, "nullable": bool}`
- `ALTER_DEFAULT`: `payload = {"name": col, "default": expr_or_none}`
- `ADD_INDEX`: `payload["index"]` contains index descriptor
- `DROP_INDEX`: `payload["name"]`
- `ADD_FK`: `payload["fk"]` contains foreign key descriptor
- `DROP_FK`: `payload["name"]`
- `ADD_UNIQUE`: `payload["columns"]: List[str]`
- `DROP_UNIQUE`: `payload["columns"]: List[str]`
- `ADD_CHECK`: `payload = {"name": cname, "expr": sql}`
- `DROP_CHECK`: `payload = {"name": cname}`

## Rename hints

You can provide rename hints to map column names and avoid drop+add sequences.

```yaml
renames:
  users.old_name: users.new_name
```

The diff also uses a simple type-compatibility heuristic as a fallback to infer renames.

## Example

```python
from schema_agent.adapters.sqlalchemy.adapter import SQLAlchemyAdapter
from schema_agent.core.diff import diff_ir
from schema_agent.policy.hints import load_schema_hints

adapter = SQLAlchemyAdapter()
base_ir = adapter.emit_ir("./examples/before", "examples.before.models")
head_ir = adapter.emit_ir("./examples/after",  "examples.after.models")
hints = load_schema_hints("./schema_hints.yml")

ops = diff_ir(base_ir, head_ir, hints)
for op in ops:
    print(op.kind, op.table, op.payload)
```