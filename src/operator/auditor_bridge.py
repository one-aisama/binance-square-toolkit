"""Auditor bridge: pre-execute validation of authored plan.

Wraps the existing PlanAuditor for use by the operator. The --execute
command also re-audits, but this bridge provides early rejection before
spending time on the execute subprocess.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.runtime.agent_config import load_active_agent
from src.runtime.agent_plan import AgentPlan
from src.runtime.cycle_policy import CycleDirective
from src.runtime.persona_policy import load_persona_policy
from src.runtime.plan_auditor import PlanAuditor
from src.runtime.plan_io import load_pending_plan
from src.runtime.post_registry import get_recent_agent_posts, get_recent_other_agent_posts

logger = logging.getLogger("bsq.operator.auditor_bridge")


def audit_authored_plan(
    agent_id: str,
    config_path: str,
) -> tuple[bool, list[str]]:
    """Audit the authored plan (with text) before execution.

    Returns (valid, issues). If valid=False, issues contains rejection reasons.
    """
    try:
        plan_data = load_pending_plan(agent_id)
        plan = AgentPlan(actions=plan_data.get("actions", []))
    except (FileNotFoundError, ValueError) as exc:
        return False, [f"Cannot load plan: {exc}"]

    try:
        agent = load_active_agent(config_path)
        policy_path = Path(f"config/persona_policies/{agent.agent_id}.yaml")
        if policy_path.exists():
            agent._policy = load_persona_policy(policy_path)
        else:
            agent._policy = None
    except Exception as exc:
        return False, [f"Cannot load agent config: {exc}"]

    directive_data = plan_data.get("directive", {})
    directive = CycleDirective(
        stage=directive_data.get("stage", "default"),
        target_comments=directive_data.get("target_comments", 0),
        target_likes=directive_data.get("target_likes", 0),
        target_posts=directive_data.get("target_posts", 0),
        target_follows=directive_data.get("target_follows", 0),
        interval_minutes=tuple(agent.cycle_interval_minutes),
    )

    recent_other = get_recent_other_agent_posts(agent_id)
    recent_self = get_recent_agent_posts(agent_id)

    auditor = PlanAuditor()
    result = auditor.audit(
        plan,
        agent=agent,
        context=None,
        directive=directive,
        recent_other_posts=recent_other,
        recent_self_posts=recent_self,
    )

    if result.valid:
        logger.info("Pre-execute audit passed for %s", agent_id)
    else:
        logger.warning("Pre-execute audit rejected for %s: %s", agent_id, result.messages())

    return result.valid, result.messages()
