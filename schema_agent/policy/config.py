from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import yaml
from pydantic import ValidationError

from .config_schema import CLIConfig


def load_cli_config(path: Optional[str]) -> Dict:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        cfg_raw = yaml.safe_load(p.read_text()) or {}
        if not isinstance(cfg_raw, dict):
            return {}
        # Validate and normalize using Pydantic schema; return dict to keep callers stable
        try:
            validated = CLIConfig(**cfg_raw)
            return validated.model_dump(exclude_none=True)
        except ValidationError:
            # If validation fails, fall back to permissive dict to avoid breaking existing users
            return cfg_raw
    except Exception:
        return {}


