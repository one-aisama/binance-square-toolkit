"""Plan I/O: save and load pending plans for agent text authoring.

Flow:
1. session_run --prepare saves plan (brief_context, no text)
2. Agent session reads plan, writes text, saves back
3. session_run --execute loads plan (with text), executes
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.runtime.agent_plan import AgentAction, AgentPlan

logger = logging.getLogger("bsq.plan_io")

RUNTIME_DIR = Path("data/runtime")
PLAN_FILENAME = "pending_plan.json"


def _plan_path(agent_id: str) -> Path:
    return RUNTIME_DIR / agent_id / PLAN_FILENAME


def save_pending_plan(
    *,
    agent_id: str,
    plan: AgentPlan,
    directive: Any,
    context_files: dict[str, str],
) -> str:
    """Save plan skeleton (without text) for agent to author.

    Returns path to the saved file.
    """
    plan_dir = RUNTIME_DIR / agent_id
    plan_dir.mkdir(parents=True, exist_ok=True)
    path = _plan_path(agent_id)

    payload = {
        "agent_id": agent_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "directive": {
            "stage": getattr(directive, "stage", ""),
            "target_comments": getattr(directive, "target_comments", 0),
            "target_likes": getattr(directive, "target_likes", 0),
            "target_posts": getattr(directive, "target_posts", 0),
            "target_follows": getattr(directive, "target_follows", 0),
        },
        "context_files": context_files,
        "actions": [action.model_dump() for action in plan.sorted_actions()],
    }

    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Saved pending plan: %s (%d actions)", path, len(plan.actions))
    return str(path)


def load_pending_plan(agent_id: str) -> dict[str, Any]:
    """Load pending plan from disk. Returns raw dict with actions list.

    Raises FileNotFoundError if no pending plan exists.
    """
    path = _plan_path(agent_id)
    if not path.exists():
        raise FileNotFoundError(f"No pending plan at {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    logger.info("Loaded pending plan: %s (%d actions)", path, len(payload.get("actions", [])))
    return payload


def update_pending_plan(agent_id: str, actions: list[dict[str, Any]]) -> str:
    """Update actions in pending plan (agent fills in text). Returns path."""
    path = _plan_path(agent_id)
    if not path.exists():
        raise FileNotFoundError(f"No pending plan at {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["actions"] = actions
    payload["text_authored_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Updated pending plan with text: %s", path)
    return str(path)


def plan_has_text(agent_id: str) -> bool:
    """Check if pending plan has text filled in for all comment/post actions."""
    path = _plan_path(agent_id)
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    for action_data in payload.get("actions", []):
        action_type = action_data.get("action", "")
        text = (action_data.get("text") or "").strip()
        if action_type in {"comment", "post", "quote_repost"} and not text:
            return False
    return True


def load_plan_for_execution(agent_id: str) -> AgentPlan:
    """Load pending plan and convert to AgentPlan for execution.

    Validates that text-requiring actions have text filled in.
    Raises ValueError if text is missing.
    """
    payload = load_pending_plan(agent_id)
    actions = payload.get("actions", [])

    missing_text = []
    for action_data in actions:
        action_type = action_data.get("action", "")
        text = (action_data.get("text") or "").strip()
        if action_type in {"comment", "post", "quote_repost"} and not text:
            target = action_data.get("target") or action_data.get("brief_context", "")[:50]
            missing_text.append(f"{action_type} → {target}")

    if missing_text:
        raise ValueError(
            f"Plan has {len(missing_text)} actions without text. "
            f"Agent must write text before execution: {missing_text}"
        )

    return AgentPlan(actions=actions)


def delete_pending_plan(agent_id: str) -> None:
    """Remove pending plan after successful execution."""
    path = _plan_path(agent_id)
    if path.exists():
        path.unlink()
        logger.info("Deleted pending plan: %s", path)
