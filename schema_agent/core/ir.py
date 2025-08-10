from __future__ import annotations

from typing import Dict, List, Optional, Literal
from pydantic import BaseModel, Field
from pydantic import BaseModel

Dialect = Literal["postgresql"]


class Column(BaseModel):
    name: str
    data_type: str
    nullable: bool
    default: Optional[str] = None
    generated: Optional[str] = None
    collation: Optional[str] = None
    comment: Optional[str] = None


class Index(BaseModel):
    name: str
    columns: List[str]
    unique: bool = False
    method: str = "btree"
    include: List[str] = Field(default_factory=list)


class ForeignKey(BaseModel):
    name: str
    columns: List[str]
    ref_table: str
    ref_columns: List[str]
    on_delete: Optional[str] = None
    on_update: Optional[str] = None
    deferrable: bool = False
    initially_deferred: bool = False


class Table(BaseModel):
    name: str
    columns: Dict[str, Column]
    primary_key: List[str] = Field(default_factory=list)
    uniques: List[List[str]] = Field(default_factory=list)
    checks: Dict[str, str] = Field(default_factory=dict)
    indexes: Dict[str, Index] = Field(default_factory=dict)
    fks: Dict[str, ForeignKey] = Field(default_factory=dict)
    partitioning: Optional[str] = None
    comment: Optional[str] = None


class IR(BaseModel):
    dialect: Dialect
    version: Optional[str] = None
    tables: Dict[str, Table]
    enums: Dict[str, List[str]] = Field(default_factory=dict)
    extensions: List[str] = Field(default_factory=list)


