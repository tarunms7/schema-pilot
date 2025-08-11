from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class CLIConfig(BaseModel):
    adapter: str = Field(default="sqlalchemy")
    dialect: str = Field(default="postgresql")

    base_dir: str
    head_dir: str

    base_module: Optional[str] = None
    head_module: Optional[str] = None

    schema_hints: Optional[str] = None

    fail_on_unsafe: bool = Field(default=False)
    summary_only: bool = Field(default=False)
    summary_json: Optional[str] = None

    class Config:
        extra = "allow"


