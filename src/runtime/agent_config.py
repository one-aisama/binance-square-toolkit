"""Runtime configuration for the active Binance Square agent.

Single-agent mode uses one checked-in YAML file as the operational source of truth.
This keeps profile binding, agent identity, and docs aligned across sessions.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator


class SessionMinimumConfig(BaseModel):
    """Minimum actions the agent must complete before finishing a session."""

    like: int = 20
    comment: int = 20
    post: int = 3

    def as_dict(self) -> dict[str, int]:
        return {"like": self.like, "comment": self.comment, "post": self.post}


class TARequestConfig(BaseModel):
    """Technical-analysis request definition for session context."""

    symbol: str
    timeframe: str = "4H"


class VisualConfig(BaseModel):
    """Runtime configuration for AI-generated visuals."""

    enabled: bool = True
    provider: str = "chatgpt_web"
    provider_url: str = "https://chatgpt.com/"
    profile_path: str | None = None
    output_dir: str = "data/generated_visuals"
    prompt_timeout_sec: int = 180
    viewport_width: int = 1536
    viewport_height: int = 960


class ModeOverride(BaseModel):
    """Individual-mode overlay: overrides specific agent config fields."""

    label: str = ""
    expires_at: datetime | None = None
    market_symbols: list[str] | None = None
    session_minimum: dict[str, int] | None = None
    coin_bias_preferred: list[str] | None = None
    coin_bias_exclude_from_posts: list[str] | None = None
    target_posts_override: int | None = None
    target_comments_override: int | None = None
    target_likes_override: int | None = None
    style_notes: list[str] = Field(default_factory=list)


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
    max_session_actions: int = 80
    session_minimum: SessionMinimumConfig = Field(default_factory=SessionMinimumConfig)
    market_symbols: list[str] = Field(
        default_factory=lambda: ["BTC", "ETH", "SOL", "BNB", "XRP"]
    )
    ta_requests: list[TARequestConfig] = Field(
        default_factory=lambda: [
            TARequestConfig(symbol="BTC", timeframe="1D"),
            TARequestConfig(symbol="ETH", timeframe="4H"),
            TARequestConfig(symbol="SOL", timeframe="4H"),
        ]
    )
    visual: VisualConfig = Field(default_factory=VisualConfig)
    cycle_interval_minutes: list[int] = Field(default_factory=lambda: [20, 35])
    daily_plan_timezone: str = "UTC"
    notes: str = ""
    mode: Literal["standard", "individual", "test"] = "standard"
    mode_override: ModeOverride | None = None

    def effective_config(self) -> "ActiveAgentConfig":
        """Resolve individual-mode overrides into a merged config.

        Standard/test → returns self unchanged.
        Individual with expired override → returns self unchanged.
        Individual with active override → returns copy with merged fields.
        """
        if self.mode != "individual" or not self.mode_override:
            return self
        ovr = self.mode_override
        if ovr.expires_at and ovr.expires_at < datetime.now(timezone.utc):
            return self

        updates: dict = {}
        if ovr.market_symbols is not None:
            updates["market_symbols"] = ovr.market_symbols
        if ovr.session_minimum is not None:
            merged = self.session_minimum.as_dict()
            merged.update(ovr.session_minimum)
            updates["session_minimum"] = SessionMinimumConfig(**merged)
        return self.model_copy(update=updates) if updates else self

    @field_validator("primary_feed_tab")
    @classmethod
    def validate_feed_tab(cls, value: str) -> str:
        if value not in {"recommended", "following"}:
            raise ValueError("primary_feed_tab must be 'recommended' or 'following'")
        return value

    @field_validator("cycle_interval_minutes")
    @classmethod
    def validate_cycle_interval(cls, value: list[int]) -> list[int]:
        if len(value) != 2:
            raise ValueError("cycle_interval_minutes must contain exactly two integers")
        if value[0] <= 0 or value[1] <= 0:
            raise ValueError("cycle_interval_minutes values must be positive")
        if value[0] > value[1]:
            raise ValueError("cycle_interval_minutes must be ordered min,max")
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
