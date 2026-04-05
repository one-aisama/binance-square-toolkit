"""Shared test helpers for creating mock agents with persona policies."""

from pathlib import Path
from types import SimpleNamespace

from src.runtime.persona_policy import load_persona_policy

_POLICY_DIR = Path("config/persona_policies")


def make_agent(agent_id: str, **overrides) -> SimpleNamespace:
    """Create a mock agent SimpleNamespace with persona policy attached."""
    policy_path = _POLICY_DIR / f"{agent_id}.yaml"
    policy = load_persona_policy(policy_path) if policy_path.exists() else None

    defaults = {
        "agent_id": agent_id,
        "agent_dir": f"agents/{agent_id}",
        "_policy": policy,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)
