from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import yaml


def load_schema_hints(path: Optional[str]) -> Dict:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        content = yaml.safe_load(p.read_text()) or {}
        if not isinstance(content, dict):
            return {}
        # normalize helpful derived values
        dialect = content.get("dialect", {}).get("postgres", {})
        target_version = dialect.get("target_version")
        if target_version:
            try:
                major = int(str(target_version).split(".")[0])
            except Exception:
                major = None
            content.setdefault("_derived", {})["pg_major"] = major
        return content
    except Exception:
        return {}


