# Intermediate Representation (IR)

The IR is a normalized, dialect-aware snapshot of your database schema extracted from code. It is represented using Pydantic models in `schema_agent.core.ir`.

## Models

```python
from schema_agent.core.ir import IR, Table, Column, Index, ForeignKey
```

- `IR`:
  - `dialect: Literal["postgresql"]`
  - `version: Optional[str]`
  - `tables: Dict[str, Table]`
  - `enums: Dict[str, List[str]] = {}`
  - `extensions: List[str] = []`

- `Table`:
  - `name: str`
  - `columns: Dict[str, Column]`
  - `primary_key: List[str]`
  - `uniques: List[List[str]]`
  - `checks: Dict[str, str]`
  - `indexes: Dict[str, Index]`
  - `fks: Dict[str, ForeignKey]`
  - `partitioning: Optional[str]`
  - `comment: Optional[str]`

- `Column`:
  - `name: str`
  - `data_type: str`
  - `nullable: bool`
  - `default: Optional[str]`
  - `generated: Optional[str]`
  - `collation: Optional[str]`
  - `comment: Optional[str]`

- `Index`:
  - `name: str`
  - `columns: List[str]`
  - `unique: bool = False`
  - `method: str = "btree"`
  - `include: List[str] = []`

- `ForeignKey`:
  - `name: str`
  - `columns: List[str]`
  - `ref_table: str`
  - `ref_columns: List[str]`
  - `on_delete: Optional[str]`
  - `on_update: Optional[str]`
  - `deferrable: bool = False`
  - `initially_deferred: bool = False`

## Example

```python
from schema_agent.adapters.sqlalchemy.adapter import SQLAlchemyAdapter
adapter = SQLAlchemyAdapter()
ir = adapter.emit_ir(repo_path="./examples/after", module_hint="examples.after.models")
print(ir.model_dump_json(indent=2))
```