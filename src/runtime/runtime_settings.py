from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DEFAULT_RUNTIME_SETTINGS_PATH = "config/settings.yaml"


def load_runtime_settings(path: str = DEFAULT_RUNTIME_SETTINGS_PATH) -> dict[str, Any]:
    settings_path = Path(path)
    if not settings_path.exists():
        return {}
    with settings_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}
