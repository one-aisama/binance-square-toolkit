"""Runtime configuration for the active Binance Square agent.

Single-agent mode uses one checked-in YAML file as the operational source of truth.
This keeps profile binding, agent identity, and docs aligned across sessions.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, field_validator


class ActiveAgentConfig(BaseModel):
    """Runtime binding between the active agent and the AdsPower profile."""

    agent_id: str
    binance_username: str
    profile_serial: str
    adspower_user_id: str
    persona_id: str
    agent_dir: str
    account_config_path: str
    primary_feed_tab: str = "recommended"
    notes: str = ""

    @field_validator("primary_feed_tab")
    @classmethod
    def validate_feed_tab(cls, value: str) -> str:
        if value not in {"recommended", "following"}:
            raise ValueError("primary_feed_tab must be 'recommended' or 'following'")
        return value


class RuntimeConfig(BaseModel):
    """Top-level runtime config file structure."""

    active_agent: ActiveAgentConfig


def load_active_agent(path: str = "config/active_agent.yaml") -> ActiveAgentConfig:
    """Load the current active agent runtime config from YAML."""
    cfg_path = Path(path)
    if not cfg_path.exists():
        raise FileNotFoundError(f"Active agent config not found: {path}")

    with cfg_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    config = RuntimeConfig(**data)
    return config.active_agent
