"""Media policy: rules for when and what type of visual to attach.

Used by PlanAuditor for validation and by other modules for visual recommendations.
"""

from __future__ import annotations

from typing import Any

IMAGE_VISUAL_TYPES = {
    "chart_capture",
    "chart_image",
    "editorial_card",
    "image",
    "news_card",
    "page_capture",
    "reaction_card",
}

# Action types that require an attached image
_IMAGE_REQUIRED_ACTIONS = {"post"}

# Action types that must NOT have an image
_IMAGE_FORBIDDEN_ACTIONS = {"comment", "quote_repost"}


def should_attach_image(
    agent_id: str,
    *,
    action_type: str = "post",
    recent_posts: list[dict[str, Any]] | None = None,
) -> bool:
    """Whether this action requires an attached image.

    Rules:
    - All posts (market, news, editorial, opinion) → image required
    - Comments → no image
    - Quote reposts → no image
    """
    del agent_id, recent_posts
    return action_type in _IMAGE_REQUIRED_ACTIONS


def is_image_visual(visual_type: str | None) -> bool:
    """Check if the given visual_type qualifies as an image attachment."""
    return str(visual_type or "").lower() in IMAGE_VISUAL_TYPES


def recommend_visual_kind(
    post_family: str,
    *,
    has_price_data: bool = False,
    has_coin: bool = False,
) -> str:
    """Recommend which visual_kind to use based on post content.

    Rules:
    - market_chart or price-related → chart_capture (screenshot of chart)
    - news with price data → chart_capture
    - news without price → news_card (AI-generated card)
    - coin post without price → editorial_card (AI art)
    - editorial/opinion → reaction_card
    """
    if post_family == "market_chart":
        return "chart_capture"
    if post_family == "news_reaction":
        return "chart_capture" if has_price_data and has_coin else "news_card"
    if has_coin and has_price_data:
        return "chart_capture"
    if has_coin:
        return "editorial_card"
    return "reaction_card"
