"""Session planner — generates a concrete action plan for the agent.

Bootstrap phase: deterministic plan from feed data (no LLM needed).
Normal phase: prepare_context() returns structured text for the agent
(Claude session) to read and decide the plan itself.
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("bsq.strategy.planner")

VALID_ACTIONS = {"post", "comment", "like", "follow", "quote_repost"}
REQUIRED_FIELDS = {"action", "priority"}
ACTIONS_REQUIRING_TARGET = {"comment", "like", "follow", "quote_repost"}


def _read_file(path: str) -> str:
    """Read a text file, return empty string if not found."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


class SessionPlanner:
    """Creates a concrete action plan for an agent session."""

    def __init__(self, agent_dir: str):
        self._agent_dir = agent_dir

    def create_plan(
        self,
        filtered_feed: list[dict],
        market_data: dict,
        news: list[dict],
        is_bootstrap: bool = False,
    ) -> list[dict]:
        """Create a deterministic bootstrap plan from feed data.

        Use this only during bootstrap phase. For normal sessions,
        use prepare_context() and let the agent decide the plan.

        Args:
            filtered_feed: Pre-filtered feed posts from feed_filter.
            market_data: Current market data dict (unused in bootstrap).
            news: Recent crypto news headlines (unused in bootstrap).
            is_bootstrap: Must be True. Exists for backward compatibility.

        Returns:
            List of action dicts sorted by priority.
        """
        plan = self._build_bootstrap_plan(filtered_feed)
        logger.info(
            "SessionPlanner.create_plan: bootstrap plan, actions=%d",
            len(plan),
        )
        return plan

    def prepare_context(
        self,
        filtered_feed: list[dict],
        market_data: dict,
        news: list[dict],
    ) -> str:
        """Prepare structured context for the agent to create a plan.

        The agent (Claude session) reads this and decides the plan itself.
        Returns formatted text with all the info needed for planning.

        Args:
            filtered_feed: Pre-filtered feed posts from feed_filter.
            market_data: Current market data dict.
            news: Recent crypto news headlines.

        Returns:
            Formatted markdown string with strategy, feed, market, news context.
        """
        strategy = _read_file(str(Path(self._agent_dir) / "strategy.md"))
        lessons = _read_file(str(Path(self._agent_dir) / "lessons.md"))
        relationships = _read_file(str(Path(self._agent_dir) / "relationships.md"))

        feed_lines = []
        for p in filtered_feed[:20]:
            preview = (p.get("text") or "")[:120].replace("\n", " ")
            fit = p.get("selection_reason") or "general"
            feed_lines.append(
                f"- post_id={p.get('post_id')}, author={p.get('author')}, "
                f"likes={p.get('like_count', 0)}, fit={fit}, text: {preview}"
            )
        feed_str = "\n".join(feed_lines) if feed_lines else "(empty feed)"

        market_str = json.dumps(market_data, indent=2) if market_data else "(no data)"

        news_lines = []
        for n in (news or [])[:10]:
            title = n.get("title") or n.get("headline") or str(n)
            news_lines.append(f"- {title}")
        news_str = "\n".join(news_lines) if news_lines else "(no news)"

        sections = [
            "# Session Planning Context",
            "",
            "## Current Strategy",
            strategy if strategy else "(no strategy.md yet)",
            "",
            "## Lessons Learned",
            lessons if lessons else "(no lessons yet)",
            "",
            "## Relationships",
            relationships if relationships else "(no relationships yet)",
            "",
            "## Available Feed Posts (already prioritized for this agent)",
            feed_str,
            "",
            "## Market Data",
            market_str,
            "",
            "## News",
            news_str,
            "",
            "## Plan Format",
            "Each action in the plan should have:",
            '- "action": "post" | "comment" | "like" | "follow" | "quote_repost"',
            '- "target": post_id (required for comment/like/follow/quote_repost)',
            '- "target_author": author name if applicable',
            '- "priority": 1-5 (1 = highest)',
            '- "reason": why this action',
            '- "fallback": alternative action if this fails, or null',
            '- "text": final agent-authored wording for post/comment/quote_repost, or null for like/follow',
            '- "coin": optional Binance chart-card ticker like BTC for post actions',
            '- "chart_symbol": optional trading pair like BTC_USDT, only when chart_image=true',
            '- "chart_image": optional boolean, true only when you explicitly want a custom screenshot instead of a chart card',
            '- "image_path": optional local image path for a custom visual; never combine it with coin',
            "",
            "## Guidelines",
            "- Respect the minimum contract shown in the live session context",
            "- Each comment must target a specific post_id from the feed",
            "- Post/comment/quote actions must include final text written by the agent",
            "- Prefer coin chart cards for routine market takes; use chart_image only when the pair/timeframe itself matters",
            "- Never combine coin with chart_image or image_path in one post",
            "- Avoid repetitive visuals across consecutive posts, especially the same pair and timeframe",
            "- Scripts may execute the plan, but must never draft the wording for you",
            "- Order by priority (1 = highest)",
        ]

        context = "\n".join(sections)
        logger.info(
            "SessionPlanner.prepare_context: prepared context, "
            "feed_posts=%d, has_market=%s, news_count=%d",
            len(filtered_feed),
            bool(market_data),
            len(news or []),
        )
        return context

    def _build_bootstrap_plan(self, filtered_feed: list[dict]) -> list[dict]:
        """Build a deterministic plan for bootstrap phase (no LLM needed).

        Picks top posts by like_count for comments/likes, adds a generic
        post action and an optional follow.
        """
        sorted_feed = sorted(
            filtered_feed, key=lambda p: p.get("like_count", 0), reverse=True
        )

        plan: list[dict[str, Any]] = []

        # 1 post action
        plan.append({
            "action": "post",
            "target": None,
            "target_author": None,
            "priority": 2,
            "reason": "Daily content — market analysis with chart",
            "fallback": None,
            "content_hint": "Market analysis of top mover today with TA data",
            "image_type": "chart",
        })

        # 3 comment actions on top posts
        for i, post in enumerate(sorted_feed[:3]):
            plan.append({
                "action": "comment",
                "target": post.get("post_id"),
                "target_author": post.get("author"),
                "priority": 1,
                "reason": f"Engage with high-visibility post (likes={post.get('like_count', 0)})",
                "fallback": None,
                "content_hint": None,
                "image_type": None,
            })

        # 5 like actions (includes the 3 we comment on + 2 more)
        for i, post in enumerate(sorted_feed[:5]):
            plan.append({
                "action": "like",
                "target": post.get("post_id"),
                "target_author": post.get("author"),
                "priority": 3,
                "reason": "Support content we engage with",
                "fallback": None,
                "content_hint": None,
                "image_type": None,
            })

        # 1 follow action — highest follower author if available
        authors_with_followers = [
            p for p in sorted_feed if p.get("author_followers")
        ]
        if authors_with_followers:
            top_author = max(
                authors_with_followers,
                key=lambda p: p.get("author_followers", 0),
            )
            plan.append({
                "action": "follow",
                "target": None,
                "target_author": top_author.get("author"),
                "priority": 4,
                "reason": f"Follow high-value author ({top_author.get('author_followers')} followers)",
                "fallback": None,
                "content_hint": None,
                "image_type": None,
            })

        plan.sort(key=lambda a: a.get("priority", 99))
        logger.info(
            "SessionPlanner._build_bootstrap_plan: %d actions from %d feed posts",
            len(plan),
            len(filtered_feed),
        )
        return plan

    def validate_plan(self, plan: list[dict]) -> list[dict]:
        """Validate and clean plan actions.

        Removes actions with missing required fields or invalid action types.
        Sorts by priority.
        """
        valid = []
        for action in plan:
            if not isinstance(action, dict):
                continue
            if not REQUIRED_FIELDS.issubset(action.keys()):
                logger.warning(
                    "SessionPlanner.validate_plan: missing fields, action=%s",
                    action,
                )
                continue
            if action["action"] not in VALID_ACTIONS:
                logger.warning(
                    "SessionPlanner.validate_plan: invalid action type=%s",
                    action["action"],
                )
                continue
            if action["action"] in ACTIONS_REQUIRING_TARGET and not action.get("target"):
                logger.warning(
                    "SessionPlanner.validate_plan: %s action missing target, skipped",
                    action["action"],
                )
                continue
            valid.append(action)

        valid.sort(key=lambda a: a.get("priority", 99))
        return valid

