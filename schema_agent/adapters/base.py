from __future__ import annotations

from abc import ABC, abstractmethod
from schema_agent.core.ir import IR


class SchemaAdapter(ABC):
    @abstractmethod
    def emit_ir(self, repo_path: str, module_hint: str | None = None) -> IR:  # pragma: no cover - interface
        """Return normalized IR by loading models inside repo_path."""


