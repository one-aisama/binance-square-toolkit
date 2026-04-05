from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CHECKPOINT_DIR = Path("data/runtime")
_LEGACY_DIR = Path("data/runs")


def get_checkpoint_path(agent_id: str) -> Path:
    new_path = CHECKPOINT_DIR / agent_id / "checkpoint.json"
    if not new_path.exists():
        legacy = _LEGACY_DIR / f"{agent_id}_execution_checkpoint.json"
        if legacy.exists():
            new_path.parent.mkdir(parents=True, exist_ok=True)
            legacy.rename(new_path)
    return new_path


def load_execution_checkpoint(agent_id: str) -> dict[str, Any] | None:
    path = get_checkpoint_path(agent_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def save_execution_checkpoint(agent_id: str, payload: dict[str, Any]) -> Path:
    path = get_checkpoint_path(agent_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def clear_execution_checkpoint(agent_id: str) -> None:
    path = get_checkpoint_path(agent_id)
    if path.exists():
        path.unlink()
