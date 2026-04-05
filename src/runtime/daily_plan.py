from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

DAILY_PLAN_DIR = Path("data/runtime")
_LEGACY_PLAN_DIR = Path("data/runs")
DEFAULT_PLAN_TIMEZONE = "UTC"
TRACKED_ACTIONS = ("like", "comment", "post", "follow")
TARGET_ACTIONS = ("like", "comment", "post")


def get_daily_plan_path(agent_id: str) -> Path:
    new_path = DAILY_PLAN_DIR / agent_id / "daily_plan.json"
    if not new_path.exists():
        legacy = _LEGACY_PLAN_DIR / f"{agent_id}_daily_plan.json"
        if legacy.exists():
            new_path.parent.mkdir(parents=True, exist_ok=True)
            legacy.rename(new_path)
    return new_path


def current_plan_day(
    timezone_name: str = DEFAULT_PLAN_TIMEZONE,
    *,
    current_time: datetime | None = None,
) -> str:
    zone = ZoneInfo(timezone_name)
    now = current_time.astimezone(zone) if current_time else datetime.now(zone)
    return now.date().isoformat()


def load_daily_plan_state(
    agent_id: str,
    *,
    targets: dict[str, int],
    timezone_name: str = DEFAULT_PLAN_TIMEZONE,
    current_time: datetime | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    plan_path = path or get_daily_plan_path(agent_id)
    today = current_plan_day(timezone_name, current_time=current_time)
    payload = _load(plan_path)

    if payload.get("plan_date") != today:
        payload = _new_state(agent_id, today, targets, timezone_name, current_time=current_time)
        _write(plan_path, payload)
        return payload

    normalized = _normalize_state(payload, targets, timezone_name, current_time=current_time)
    _write(plan_path, normalized)
    return normalized


def update_daily_plan_state(
    agent_id: str,
    results: list[dict[str, Any]],
    *,
    targets: dict[str, int],
    timezone_name: str = DEFAULT_PLAN_TIMEZONE,
    current_time: datetime | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    plan_path = path or get_daily_plan_path(agent_id)
    state = load_daily_plan_state(
        agent_id,
        targets=targets,
        timezone_name=timezone_name,
        current_time=current_time,
        path=plan_path,
    )
    increments = count_daily_results(results)
    completed = dict(state.get("completed") or {})
    for action, value in increments.items():
        completed[action] = int(completed.get(action, 0)) + value

    state["completed"] = completed
    state["last_updated_at"] = _timestamp(timezone_name, current_time=current_time)
    if is_daily_plan_complete(state):
        state["status"] = "completed"
        state["completed_at"] = state["last_updated_at"]
    _write(plan_path, state)
    return state


def is_daily_plan_complete(state: dict[str, Any]) -> bool:
    targets = state.get("targets") or {}
    completed = state.get("completed") or {}
    return all(int(completed.get(action, 0)) >= int(targets.get(action, 0)) for action in TARGET_ACTIONS)


def remaining_daily_targets(state: dict[str, Any]) -> dict[str, int]:
    targets = state.get("targets") or {}
    completed = state.get("completed") or {}
    return {
        action: max(int(targets.get(action, 0)) - int(completed.get(action, 0)), 0)
        for action in TARGET_ACTIONS
    }


def count_daily_results(results: list[dict[str, Any]]) -> dict[str, int]:
    counts = {action: 0 for action in TRACKED_ACTIONS}
    for result in results:
        response = result.get("response") or {}
        action = str(result.get("action") or "")
        success = bool(result.get("success"))

        if action == "like" and success:
            counts["like"] += 1
            continue
        if action == "follow" and success:
            counts["follow"] += 1
            continue
        if action == "post" and success:
            counts["post"] += 1
            continue
        if action != "comment":
            continue

        if response.get("liked"):
            counts["like"] += 1
        if response.get("followed"):
            counts["follow"] += 1
        if response.get("commented"):
            counts["comment"] += 1
            continue
        if success and not response.get("reply_limit_exceeded") and "commented" not in response:
            counts["comment"] += 1
    return counts


def _new_state(
    agent_id: str,
    plan_date: str,
    targets: dict[str, int],
    timezone_name: str,
    *,
    current_time: datetime | None = None,
) -> dict[str, Any]:
    timestamp = _timestamp(timezone_name, current_time=current_time)
    completed = {action: 0 for action in TRACKED_ACTIONS}
    return {
        "agent_id": agent_id,
        "plan_date": plan_date,
        "timezone": timezone_name,
        "status": "completed" if all(int(targets.get(action, 0)) <= 0 for action in TARGET_ACTIONS) else "in_progress",
        "targets": {action: int(targets.get(action, 0)) for action in TARGET_ACTIONS},
        "completed": completed,
        "created_at": timestamp,
        "last_updated_at": timestamp,
        "completed_at": None,
    }


def _normalize_state(
    payload: dict[str, Any],
    targets: dict[str, int],
    timezone_name: str,
    *,
    current_time: datetime | None = None,
) -> dict[str, Any]:
    state = dict(payload)
    state.setdefault("timezone", timezone_name)
    state["targets"] = {action: int(targets.get(action, 0)) for action in TARGET_ACTIONS}
    completed = dict(state.get("completed") or {})
    for action in TRACKED_ACTIONS:
        completed[action] = int(completed.get(action, 0))
    state["completed"] = completed
    state.setdefault("created_at", _timestamp(timezone_name, current_time=current_time))
    state.setdefault("last_updated_at", _timestamp(timezone_name, current_time=current_time))
    state.setdefault("completed_at", None)
    state["status"] = "completed" if is_daily_plan_complete(state) else "in_progress"
    return state


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _timestamp(timezone_name: str, *, current_time: datetime | None = None) -> str:
    zone = ZoneInfo(timezone_name)
    now = current_time.astimezone(zone) if current_time else datetime.now(zone)
    return now.isoformat()
