from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.runtime.content_fingerprint import infer_comment_domain, is_market_discussion
from src.strategy.planner import SessionPlanner

logger = logging.getLogger("bsq.runtime.session_context")


class ReplyCandidate(BaseModel):
    post_id: str
    author_handle: str
    text: str
    my_comment: str = ""


class FeedCandidate(BaseModel):
    post_id: str
    author: str
    text: str
    like_count: int = 0
    tab: str
    selection_reason: str = ""


class SessionContext(BaseModel):
    agent_id: str
    binance_username: str
    minimum: dict[str, int]
    minimum_status: dict[str, dict[str, int]]
    my_stats: dict[str, Any] = Field(default_factory=dict)
    market_data: dict[str, Any] = Field(default_factory=dict)
    news: list[dict[str, Any]] = Field(default_factory=list)
    ta: dict[str, dict[str, Any]] = Field(default_factory=dict)
    replies: list[ReplyCandidate] = Field(default_factory=list)
    feed_posts: list[FeedCandidate] = Field(default_factory=list)
    planning_context: str = ""


class SessionContextBuilder:
    """Read-only builder for the live agent session context."""

    def __init__(self, agent_dir: str, primary_limit: int = 60, secondary_limit: int = 30):
        self._planner = SessionPlanner(agent_dir)
        self._primary_limit = primary_limit
        self._secondary_limit = secondary_limit

    async def build(self, sdk: Any, agent: Any) -> SessionContext:
        market_symbols = getattr(agent, "market_symbols", ["BTC", "ETH", "SOL", "BNB", "XRP"])
        ta_requests = getattr(agent, "ta_requests", [])
        market_data = await self._safe_call(sdk.get_market_data, market_symbols, default={})
        news = await self._safe_call(sdk.get_crypto_news, limit=5, default=[])
        ta = await self._collect_ta(sdk, ta_requests)
        my_stats = await self._safe_call(sdk.get_my_stats, default={})
        replies = await self._collect_replies(sdk, agent.binance_username)
        feed_posts = await self._collect_feed(sdk, agent)
        planning_context = self._planner.prepare_context(
            filtered_feed=[post.model_dump(exclude={"tab"}) for post in feed_posts],
            market_data=market_data,
            news=news,
        )
        return SessionContext(
            agent_id=agent.agent_id,
            binance_username=agent.binance_username,
            minimum=agent.session_minimum.as_dict(),
            minimum_status=sdk.get_minimum_status(),
            my_stats=my_stats,
            market_data=market_data,
            news=news,
            ta=ta,
            replies=replies,
            feed_posts=feed_posts,
            planning_context=planning_context,
        )

    async def _collect_ta(self, sdk: Any, ta_requests: list[Any]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for request in ta_requests:
            symbol = getattr(request, "symbol", "")
            timeframe = getattr(request, "timeframe", "4H")
            if not symbol:
                continue
            summary = await self._safe_call(sdk.get_ta_summary, symbol, timeframe, default={})
            if summary:
                result[f"{symbol}_{timeframe}"] = summary
        return result

    async def _collect_replies(self, sdk: Any, username: str) -> list[ReplyCandidate]:
        raw_replies = await self._safe_call(sdk.get_my_comment_replies, username=username, default=[])
        flattened: list[ReplyCandidate] = []
        for block in raw_replies:
            post_id = str(block.get("comment_post_id", "")).strip()
            my_comment = block.get("comment_text", "")
            for reply in block.get("replies", []):
                handle = str(reply.get("author_handle", "")).strip()
                text = str(reply.get("text", "")).strip()
                if not post_id or not handle or not text:
                    continue
                flattened.append(
                    ReplyCandidate(
                        post_id=post_id,
                        author_handle=handle,
                        text=text,
                        my_comment=my_comment,
                    )
                )
        return flattened

    async def _collect_feed(self, sdk: Any, agent: Any) -> list[FeedCandidate]:
        primary_tab = agent.primary_feed_tab
        secondary_tab = "following" if primary_tab == "recommended" else "recommended"
        primary_posts = await self._safe_call(
            sdk.get_feed_posts,
            count=self._primary_limit,
            tab=primary_tab,
            default=[],
        )
        secondary_posts = await self._safe_call(
            sdk.get_feed_posts,
            count=self._secondary_limit,
            tab=secondary_tab,
            default=[],
        )
        combined = self._prepare_posts(primary_posts, primary_tab)
        combined.extend(self._prepare_posts(secondary_posts, secondary_tab))
        return self._prioritize_posts(self._dedupe_posts(combined), agent)

    async def _safe_call(self, func: Any, *args: Any, default: Any, **kwargs: Any) -> Any:
        try:
            return await func(*args, **kwargs)
        except Exception as exc:
            logger.warning("session context call failed: %s", exc)
            return default

    def _prepare_posts(self, posts: list[dict[str, Any]], tab: str) -> list[FeedCandidate]:
        prepared: list[FeedCandidate] = []
        feed_cfg = getattr(self, "_feed_config", None)
        spam_words = set(feed_cfg.spam_words) if feed_cfg else {
            "gift", "giveaway", "airdrop", "copy trading",
            "free crypto", "claim", "join my vip", "signal group",
        }
        min_text = feed_cfg.min_text_length if feed_cfg else 40
        max_text = feed_cfg.max_text_length if feed_cfg else 400
        for post in posts or []:
            text = str(post.get("text", "")).strip()
            post_id = str(post.get("post_id", "")).strip()
            if not post_id or len(text) < min_text:
                continue
            text_lower = text.lower()
            if any(word in text_lower for word in spam_words):
                continue
            prepared.append(
                FeedCandidate(
                    post_id=post_id,
                    author=str(post.get("author", "")).strip(),
                    text=text[:max_text],
                    like_count=int(post.get("like_count", 0) or 0),
                    tab=tab,
                )
            )
        prepared.sort(key=lambda post: post.like_count, reverse=True)
        return prepared

    def _dedupe_posts(self, posts: list[FeedCandidate]) -> list[FeedCandidate]:
        seen: set[str] = set()
        deduped: list[FeedCandidate] = []
        for post in posts:
            if post.post_id in seen:
                continue
            seen.add(post.post_id)
            deduped.append(post)
        return deduped

    def _prioritize_posts(self, posts: list[FeedCandidate], agent: Any) -> list[FeedCandidate]:
        ranked: list[tuple[int, int, FeedCandidate]] = []
        for post in posts:
            score, reason = self._score_post_for_agent(post, agent)
            ranked.append(
                (
                    score,
                    post.like_count,
                    post.model_copy(update={"selection_reason": reason}),
                )
            )
        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [post for _, _, post in ranked]

    def _score_post_for_agent(self, post: FeedCandidate, agent: Any) -> tuple[int, str]:
        score = post.like_count
        reasons: list[str] = []
        text = post.text.lower()
        text_upper = post.text.upper()
        topic = infer_comment_domain(post.text)

        if post.tab == getattr(agent, "primary_feed_tab", "recommended"):
            score += 15

        policy = getattr(agent, "_policy", None) or getattr(self, "_policy", None)
        if not policy:
            return score, "general"

        preferred_symbols = [s.upper() for s in getattr(agent, "market_symbols", [])]
        hits = [symbol for symbol in preferred_symbols if self._has_symbol(text_upper, symbol)]

        # Apply keyword bonuses
        for keyword, bonus in policy.feed_scoring.keyword_bonuses.items():
            if keyword in text:
                score += int(bonus)
                reasons.append(keyword)

        # Apply symbol bonus for preferred symbols
        if hits and policy.feed_scoring.symbol_bonus:
            score += int(policy.feed_scoring.symbol_bonus)
            reasons.append(f"preferred_alt:{hits[0]}")

        # Apply keyword penalties
        for keyword, penalty in policy.feed_scoring.keyword_penalties.items():
            if keyword == topic or keyword in text:
                if not hits:  # penalties don't apply when preferred symbol is present
                    score += int(penalty)
                    reasons.append(f"deprioritized_{keyword}")

        # TA bonus with preferred symbols
        if topic == "ta" and hits:
            score += 55
            reasons.append("alt_execution")

        # Off-lane general penalty
        if topic == "general" and not hits and not is_market_discussion(post.text):
            score -= 120
            reasons.append("off_lane_general")

        return score, ",".join(dict.fromkeys(reasons)) or "general"

    def _has_symbol(self, text: str, symbol: str) -> bool:
        pattern = rf"(?<![A-Z0-9])\$?{re.escape(symbol)}(?![A-Z0-9])"
        return re.search(pattern, text) is not None


def render_session_context(context: SessionContext) -> str:
    """Render saved context for the agent to read before acting."""

    minimum_lines = [f"- {name}: {value}" for name, value in context.minimum.items()]
    status_lines = []
    for action_type, status in context.minimum_status.items():
        status_lines.append(
            f"- {action_type}: {status.get('done', 0)}/{status.get('required', 0)} "
            f"(remaining={status.get('remaining', 0)})"
        )

    reply_lines = []
    for reply in context.replies[:20]:
        preview = reply.text.replace("\n", " ")[:180]
        reply_lines.append(
            f"- post_id={reply.post_id}, author={reply.author_handle}, "
            f"my_comment={reply.my_comment[:80]!r}, reply={preview!r}"
        )

    feed_lines = []
    for post in context.feed_posts[:25]:
        preview = post.text.replace("\n", " ")[:180]
        reason = f", fit={post.selection_reason}" if post.selection_reason else ""
        feed_lines.append(
            f"- post_id={post.post_id}, tab={post.tab}, author={post.author}, "
            f"likes={post.like_count}{reason}, text={preview!r}"
        )

    minimum_block = minimum_lines or ["- (not configured)"]
    status_block = status_lines or ["- (no guard status)"]
    reply_block = reply_lines or ["- (no replies found)"]
    feed_block = feed_lines or ["- (no feed candidates found)"]

    sections = [
        "# Live Session Context",
        "",
        "## Minimum Contract",
        *minimum_block,
        "",
        "## Minimum Status",
        *status_block,
        "",
        "## My Stats",
        json.dumps(context.my_stats, indent=2, ensure_ascii=False),
        "",
        "## Reply Backlog",
        *reply_block,
        "",
        "## Feed Candidates",
        *feed_block,
        "",
        "## Market Data",
        json.dumps(context.market_data, indent=2, ensure_ascii=False),
        "",
        "## News",
        json.dumps(context.news, indent=2, ensure_ascii=False),
        "",
        "## TA",
        json.dumps(context.ta, indent=2, ensure_ascii=False),
        "",
        "## Planning Context",
        context.planning_context,
        "",
        "## Contract",
        "The toolkit must not draft comment, reply, quote, or post text.",
        "Only execute wording that was explicitly authored by the agent.",
    ]
    return "\n".join(sections).strip() + "\n"


def save_session_context(
    context: SessionContext,
    output_dir: str = "data/session_context",
) -> dict[str, str]:
    """Persist collected session context as JSON and Markdown."""

    base_dir = Path(output_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = f"{timestamp}_{context.agent_id}"
    json_path = base_dir / f"{stem}.json"
    markdown_path = base_dir / f"{stem}.md"
    json_path.write_text(context.model_dump_json(indent=2), encoding="utf-8")
    markdown_path.write_text(render_session_context(context), encoding="utf-8")
    return {
        "json_path": str(json_path.resolve()),
        "markdown_path": str(markdown_path.resolve()),
    }

