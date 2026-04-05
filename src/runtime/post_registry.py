from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.runtime.agent_plan import AgentPlan
from src.runtime.content_fingerprint import (
    extract_primary_coin,
    format_signature,
    infer_angle,
    normalize_text,
    opening_signature,
    visual_type_from_action,
)

REGISTRY_PATH = Path("data/runtime/post_registry.json")


def get_recent_other_agent_posts(
    agent_id: str,
    *,
    hours: int = 24,
    path: Path = REGISTRY_PATH,
) -> list[dict[str, Any]]:
    """Load recent successful post records from other agents."""
    records = _load_records(path)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    recent: list[dict[str, Any]] = []
    for record in records:
        if record.get("agent_id") == agent_id:
            continue
        created_at = _parse_timestamp(record.get("created_at"))
        if created_at is None or created_at < cutoff:
            continue
        recent.append(record)
    return recent


def get_recent_agent_posts(
    agent_id: str,
    *,
    limit: int = 10,
    path: Path = REGISTRY_PATH,
) -> list[dict[str, Any]]:
    """Load the latest successful posts published by one agent."""
    records = [record for record in _load_records(path) if record.get("agent_id") == agent_id]
    records.sort(
        key=lambda record: _parse_timestamp(record.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return records[: max(limit, 0)]


def record_completed_posts(
    agent_id: str,
    plan: AgentPlan,
    results: list[dict[str, Any]],
    *,
    path: Path = REGISTRY_PATH,
    retention_hours: int = 72,
) -> list[dict[str, Any]]:
    """Persist successful posts so agents can avoid topical overlap and self-repeat."""
    records = _load_records(path)
    actions = plan.sorted_actions()
    now = datetime.now(timezone.utc)

    for action, result in zip(actions, results):
        if action.action != "post" or not result.get("success"):
            continue
        text = action.text or ""
        resolved_visual = result.get("response", {}).get("resolved_visual", {})
        visual_kind = action.visual_kind or visual_type_from_action(action)
        records.append(
            {
                "agent_id": agent_id,
                "created_at": now.isoformat(),
                "text": text,
                "normalized_text": normalize_text(text),
                "primary_coin": extract_primary_coin(text, coin=action.coin, chart_symbol=action.chart_symbol),
                "angle": action.editorial_angle or infer_angle(text),
                "chart_symbol": action.chart_symbol,
                "chart_timeframe": action.chart_timeframe,
                "visual_type": visual_kind,
                "visual_kind": visual_kind,
                "visual_signature": resolved_visual.get("signature") or f"{visual_kind}:{opening_signature(text)}",
                "source_kind": action.source_kind,
                "source_post_id": action.source_post_id,
                "source_url": action.source_url,
                "post_family": action.post_family,
                "editorial_format": action.editorial_format,
                "opening_signature": opening_signature(text),
                "format_signature": format_signature(text),
            }
        )

    cutoff = now - timedelta(hours=retention_hours)
    records = [record for record in records if (_parse_timestamp(record.get("created_at")) or now) >= cutoff]
    _write_records(path, records)
    return records


def format_recent_post_summary(records: list[dict[str, Any]]) -> str:
    """Render recent-post overlap context for the plan generator."""
    if not records:
        return "(no recent post overlap risk found)"

    lines = []
    for record in records[:8]:
        preview = str(record.get("text", "")).replace("\n", " ")[:140]
        lines.append(
            "- agent={agent}, coin={coin}, family={family}, angle={angle}, format={fmt}, visual={visual}, chart={chart}, text={text}".format(
                agent=record.get("agent_id", "unknown"),
                coin=record.get("primary_coin") or "none",
                family=record.get("post_family") or "unknown",
                angle=record.get("angle") or "general",
                fmt=record.get("editorial_format") or record.get("format_signature") or "unknown",
                visual=record.get("visual_type") or "text",
                chart=record.get("chart_symbol") or "none",
                text=preview,
            )
        )
    return "\n".join(lines)


def _load_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _write_records(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        timestamp = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)

