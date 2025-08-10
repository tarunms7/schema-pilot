from __future__ import annotations

from typing import Callable, Dict, Optional, Tuple

# Adapters emit IR from a repo path + module hint
AdapterFactory = Callable[[], object]

# Planner and SQL generator are per-dialect callables
# planner: (base_ir, head_ir, ops, hints) -> List[Step]
# sqlgen: (steps, hints) -> Tuple[str, str, dict]
PlannerFunc = Callable[..., object]
SqlGenFunc = Callable[..., Tuple[str, str, dict]]


class AdapterRegistry:
    _registry: Dict[str, AdapterFactory] = {}

    @classmethod
    def register(cls, name: str, factory: AdapterFactory) -> None:
        cls._registry[name] = factory

    @classmethod
    def get(cls, name: str) -> Optional[AdapterFactory]:
        return cls._registry.get(name)

    @classmethod
    def names(cls) -> Tuple[str, ...]:
        return tuple(sorted(cls._registry.keys()))


class DialectRegistry:
    _planners: Dict[str, PlannerFunc] = {}
    _sqlgens: Dict[str, SqlGenFunc] = {}

    @classmethod
    def register_planner(cls, dialect: str, planner: PlannerFunc) -> None:
        cls._planners[dialect] = planner

    @classmethod
    def register_sqlgen(cls, dialect: str, sqlgen: SqlGenFunc) -> None:
        cls._sqlgens[dialect] = sqlgen

    @classmethod
    def get_planner(cls, dialect: str) -> Optional[PlannerFunc]:
        return cls._planners.get(dialect)

    @classmethod
    def get_sqlgen(cls, dialect: str) -> Optional[SqlGenFunc]:
        return cls._sqlgens.get(dialect)

    @classmethod
    def supported_dialects(cls) -> Tuple[str, ...]:
        return tuple(sorted(set(cls._planners.keys()) & set(cls._sqlgens.keys())))


# Bootstrap built-ins so existing behavior works out-of-the-box
def _bootstrap_defaults() -> None:
    # Register SQLAlchemy adapter
    from schema_agent.adapters.sqlalchemy.adapter import SQLAlchemyAdapter
    AdapterRegistry.register("sqlalchemy", SQLAlchemyAdapter)

    # Register Postgres planner + sqlgen
    from schema_agent.core.planner.postgres import plan_postgres
    from schema_agent.core.sqlgen.postgres import generate_postgres_sql

    DialectRegistry.register_planner("postgresql", plan_postgres)
    DialectRegistry.register_sqlgen("postgresql", generate_postgres_sql)


_bootstrap_defaults()


