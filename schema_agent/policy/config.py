from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import yaml


def load_cli_config(path: Optional[str]) -> Dict:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        cfg = yaml.safe_load(p.read_text()) or {}
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


