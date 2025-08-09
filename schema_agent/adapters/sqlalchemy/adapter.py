from __future__ import annotations

import importlib
import os
import sys
from dataclasses import dataclass
from types import ModuleType
from typing import Dict, List, Optional

from sqlalchemy import Index as SAIndex, Table as SATable
from sqlalchemy.dialects import postgresql as pg

from schema_agent.adapters.base import SchemaAdapter
from schema_agent.core.ir import Column, ForeignKey, IR, Index, Table


def _compile_type(sa_type) -> str:
    return sa_type.compile(dialect=pg.dialect())


def _compile_default(default) -> Optional[str]:
    if default is None:
        return None
    try:
        # server_default may be a DefaultClause with .arg possibly a TextClause
        if hasattr(default, "arg"):
            arg = default.arg
            # TextClause has .text attribute
            if hasattr(arg, "text"):
                return str(arg.text)
            try:
                return str(arg.compile(dialect=pg.dialect()))
            except Exception:
                return str(arg)
        # Fallback
        return str(default)
    except Exception:
        return str(default)


@dataclass
class LoadedModule:
    module: ModuleType
    sys_path_added: bool


def _purge_package_cache(module_hint: str) -> None:
    root_pkg = module_hint.split(".")[0]
    for key in list(sys.modules.keys()):
        if key == root_pkg or key.startswith(root_pkg + "."):
            try:
                del sys.modules[key]
            except KeyError:
                pass


def _import_models(repo_path: str, module_hint: Optional[str]) -> LoadedModule:
    if not module_hint:
        raise RuntimeError("module_hint is required for SQLAlchemy adapter in MVP")
    abs_repo = os.path.abspath(repo_path) if repo_path else None
    sys_path_added = False
    if abs_repo and abs_repo not in sys.path:
        sys.path.insert(0, abs_repo)
        sys_path_added = True
    # Ensure a fresh import space for base vs head to avoid caching collisions
    _purge_package_cache(module_hint)
    module = importlib.import_module(module_hint)
    return LoadedModule(module=module, sys_path_added=sys_path_added)


class SQLAlchemyAdapter(SchemaAdapter):
    def emit_ir(self, repo_path: str, module_hint: str | None = None) -> IR:
        loaded = _import_models(repo_path, module_hint)
        try:
            Base = getattr(loaded.module, "Base")
            metadata = Base.metadata
        finally:
            # cleanup: purge package and sys.path insertion to avoid cross-tree bleed
            _purge_package_cache(module_hint)
            if loaded.sys_path_added and sys.path and sys.path[0] == os.path.abspath(repo_path):
                sys.path.pop(0)

        tables: Dict[str, Table] = {}
        for tname, satable in metadata.tables.items():
            tables[tname] = self._emit_table_ir(satable)

        return IR(dialect="postgresql", version=None, tables=tables)

    def _emit_table_ir(self, satable: SATable) -> Table:
        columns: Dict[str, Column] = {}
        primary_key: List[str] = []
        uniques: List[List[str]] = []
        checks: Dict[str, str] = {}
        indexes: Dict[str, Index] = {}
        fks: Dict[str, ForeignKey] = {}

        # Columns and PK
        for col in satable.columns:
            columns[col.name] = Column(
                name=col.name,
                data_type=_compile_type(col.type),
                nullable=bool(col.nullable),
                default=_compile_default(col.server_default),
                generated=getattr(col, "computed", None) and "computed" or None,
                collation=getattr(col, "collation", None),
                comment=getattr(col, "comment", None),
            )
            if col.primary_key:
                primary_key.append(col.name)

        # Constraints: uniques, checks, fks
        for c in satable.constraints:
            cname = getattr(c, "name", None) or ""
            ctype = c.__class__.__name__.lower()
            if ctype == "uniqueconstraint":
                uniques.append([col.name for col in c.columns])
            elif ctype == "checkconstraint":
                try:
                    checks[cname] = str(c.sqltext.compile(dialect=pg.dialect()))
                except Exception:
                    checks[cname] = str(c.sqltext)
            elif ctype == "foreignkeyconstraint":
                local_cols = [fk.parent.name for fk in c.elements]
                remote_table = c.elements[0].column.table.name if c.elements else ""
                remote_cols = [fk.column.name for fk in c.elements]
                fks[cname or f"fk_{satable.name}_{'_'.join(local_cols)}"] = ForeignKey(
                    name=cname or f"fk_{satable.name}_{'_'.join(local_cols)}",
                    columns=local_cols,
                    ref_table=remote_table,
                    ref_columns=remote_cols,
                    on_delete=getattr(c, "ondelete", None),
                    on_update=getattr(c, "onupdate", None),
                    deferrable=bool(getattr(c, "deferrable", False)),
                    initially_deferred=bool(getattr(c, "initially", None) == "DEFERRED"),
                )

        # Indexes
        for idx in satable.indexes:  # type: SAIndex
            name = idx.name
            indexes[name] = Index(
                name=name,
                columns=[col.name for col in idx.expressions],
                unique=bool(idx.unique),
                method=(idx.dialect_options.get("postgresql", {}).get("using", "btree")),
                include=getattr(idx, "postgresql_include", []) or [],
            )

        return Table(
            name=satable.name,
            columns=columns,
            primary_key=primary_key,
            uniques=uniques,
            checks=checks,
            indexes=indexes,
            fks=fks,
            partitioning=None,
            comment=getattr(satable, "comment", None),
        )


