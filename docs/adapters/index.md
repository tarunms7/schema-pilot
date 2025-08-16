# Adapters

Adapters emit IR from source models. The default adapter supports SQLAlchemy.

## Available

- `sqlalchemy` (default): Inspects SQLAlchemy declarative `Base.metadata` to build IR. Requires `--base-module`/`--head-module` to import your models.

## Using SQLAlchemy adapter

```python
from schema_agent.adapters.sqlalchemy.adapter import SQLAlchemyAdapter
adapter = SQLAlchemyAdapter()
ir = adapter.emit_ir(repo_path="/path/to/repo", module_hint="yourapp.models")
```

CLI flags:
- `--adapter sqlalchemy`
- `--base-module`, `--head-module`: dotted import path that imports all model modules so that `Base.metadata` is populated

## Writing a custom adapter

Implement the `SchemaAdapter` interface:

```python
from schema_agent.adapters.base import SchemaAdapter
from schema_agent.core.ir import IR

class MyAdapter(SchemaAdapter):
	def emit_ir(self, repo_path: str, module_hint: str | None = None) -> IR:
		# load your models and return IR(...)
		...
```

Register it:

```python
from schema_agent.core.registry import AdapterRegistry
AdapterRegistry.register("myadapter", MyAdapter)
```

Then run with `--adapter myadapter` and provide any adapter-specific hints via your own config.