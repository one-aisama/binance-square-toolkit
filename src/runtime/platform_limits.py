from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

LIMITS_PATH = Path("data/runtime/platform_limits.json")
REPLY_LIMIT_WINDOW_DAYS = 7


def get_platform_limits(agent_id: str, *, path: Path = LIMITS_PATH) -> dict[str, Any]:
    data = _load_limits(path)
    payload = data.get(agent_id, {})
    reply_limit_until = payload.get("reply_limit_until")
    if reply_limit_until:
        expires_at = _parse_timestamp(reply_limit_until)
        if expires_at and expires_at <= datetime.now(timezone.utc):
            data.pop(agent_id, None)
            _write_limits(path, data)
            return {}
    return payload if isinstance(payload, dict) else {}


def is_reply_limited(agent_id: str, *, path: Path = LIMITS_PATH) -> bool:
    payload = get_platform_limits(agent_id, path=path)
    expires_at = _parse_timestamp(payload.get("reply_limit_until"))
    return bool(expires_at and expires_at > datetime.now(timezone.utc))


def record_reply_limit(agent_id: str, message: str, *, path: Path = LIMITS_PATH) -> dict[str, Any]:
    data = _load_limits(path)
    now = datetime.now(timezone.utc)
    payload = {
        "reply_limit_until": (now + timedelta(days=REPLY_LIMIT_WINDOW_DAYS)).isoformat(),
        "last_seen_at": now.isoformat(),
        "reply_limit_message": message,
    }
    data[agent_id] = payload
    _write_limits(path, data)
    return payload


def update_limits_from_results(agent_id: str, results: list[dict[str, Any]], *, path: Path = LIMITS_PATH) -> dict[str, Any]:
    latest: dict[str, Any] = {}
    for result in results:
        response = result.get("response") or {}
        if not isinstance(response, dict):
            continue
        if response.get("error_code") != "reply_limit_exceeded" and not response.get("reply_limit_exceeded"):
            continue
        message = str(response.get("error") or response.get("reply_limit_message") or "reply limit exceeded")
        latest = record_reply_limit(agent_id, message, path=path)
    return latest


def _load_limits(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _write_limits(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
