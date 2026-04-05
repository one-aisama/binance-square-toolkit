from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

ActionType = Literal["comment", "like", "post", "follow", "quote_repost"]
SentimentType = Literal["bullish", "bearish", "neutral"]


class AgentAction(BaseModel):
    """One explicit action authored by the agent."""

    action: ActionType
    priority: int = Field(default=3, ge=1, le=5)
    reason: str = ""
    target: str | None = None
    target_author: str | None = None
    text: str | None = None
    coin: str | None = None
    sentiment: SentimentType | None = None
    image_path: str | None = None
    chart_symbol: str | None = None
    chart_timeframe: str = "4H"
    chart_image: bool = False
    like: bool = False
    follow: bool = False
    source_kind: str | None = None
    source_post_id: str | None = None
    source_url: str | None = None
    editorial_angle: str | None = None
    editorial_format: str | None = None
    post_family: str | None = None
    visual_kind: str | None = None
    visual_title: str | None = None
    visual_subtitle: str | None = None
    visual_context: str | None = None
    capture_url: str | None = None
    capture_selectors: list[str] = Field(default_factory=list)
    capture_text_anchors: list[str] = Field(default_factory=list)
    capture_required_texts: list[str] = Field(default_factory=list)
    reservation_key: str | None = None
    brief_context: str | None = None  # serialized brief for agent to write post text
    target_text: str | None = None  # text of the post being commented on

    @model_validator(mode="after")
    def validate_contract(self) -> "AgentAction":
        if self.action in {"comment", "like", "follow", "quote_repost"} and not self.target:
            raise ValueError("target is required for comment/like/follow/quote_repost actions")
        if self.action == "quote_repost":
            if not self.text or not self.text.strip():
                raise ValueError("text is required for quote_repost actions")
        if self.action == "post" and self.target:
            raise ValueError("post actions cannot include target")
        if self.action != "comment" and (self.like or self.follow):
            raise ValueError("like/follow flags are only allowed on comment actions")
        if self.image_path and self.chart_symbol:
            raise ValueError("provide either image_path or chart_symbol, not both")
        if self.chart_image and not self.chart_symbol:
            raise ValueError("chart_symbol is required when chart_image is true")
        if self.image_path and self.chart_image:
            raise ValueError("provide either image_path or chart_image, not both")
        if self.visual_kind and (self.image_path or self.chart_image):
            raise ValueError("visual_kind cannot be combined with image_path or chart_image")
        if self.sentiment and not self.coin:
            raise ValueError("sentiment requires a coin chart card")
        if self.action == "post" and self.coin and (self.image_path or self.chart_image or self.visual_kind):
            raise ValueError("post actions must use either coin chart card or image media, not both")
        if self.visual_kind and self.action != "post":
            raise ValueError("visual_kind is only valid for post actions")
        if (self.capture_selectors or self.capture_text_anchors or self.capture_required_texts) and not self.capture_url:
            raise ValueError("capture_url is required when capture rules are provided")
        return self


class AgentPlan(BaseModel):
    """Validated plan that can be executed by the toolkit."""

    actions: list[AgentAction] = Field(default_factory=list)

    def sorted_actions(self) -> list[AgentAction]:
        return sorted(self.actions, key=lambda action: action.priority)


def load_agent_plan(path: str) -> AgentPlan:
    """Load a JSON plan authored by the agent."""
    plan_path = Path(path)
    if not plan_path.exists():
        raise FileNotFoundError(f"Agent plan not found: {path}")

    data = json.loads(plan_path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        data = {"actions": data}
    return AgentPlan(**data)
