from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from src.runtime.agent_plan import AgentPlan
from src.runtime.content_fingerprint import (
    extract_primary_coin,
    infer_comment_domain,
    is_market_discussion,
    opening_signature,
)
from src.runtime.editorial_brain import EditorialBrain
from src.runtime.platform_limits import is_reply_limited
from src.runtime.topic_reservation import build_reservation_key, reserve_topic
from src.runtime.comment_coordination import get_locked_post_ids, lock_comment_target
from src.runtime.news_cooldown import get_active_news_fingerprints
from src.runtime.errors import PlanGenerationError


@dataclass
class RevisionHints:
    """Planner repair hints derived from recent history and audit feedback."""

    force_comment_diversity: bool = False
    avoid_opening_signatures: set[str] = field(default_factory=set)
    avoid_coin_angle_pairs: set[tuple[str, str]] = field(default_factory=set)
    avoid_chart_symbols: set[str] = field(default_factory=set)


class DeterministicPlanGenerator:
    """Build a local no-key action plan from live context and agent rules."""

    def __init__(self, *, agent: Any, sdk: Any | None = None, db_path: str | None = None):
        self._agent = agent
        self._sdk = sdk
        self._db_path = db_path
        policy = getattr(agent, "_policy", None)
        self._editor = EditorialBrain(agent=agent, policy=policy)

    async def generate_plan(
        self,
        *,
        context: Any,
        directive: Any,
        recent_other_posts: list[dict[str, Any]],
        recent_self_posts: list[dict[str, Any]] | None = None,
        audit_feedback: list[str] | None = None,
        attempt_index: int = 0,
        strategic_directive: dict[str, Any] | None = None,
    ) -> AgentPlan:
        history = list(recent_self_posts or [])
        hints = self._build_revision_hints(
            audit_feedback=audit_feedback,
            recent_self_posts=history,
            recent_other_posts=recent_other_posts,
        )
        actions: list[dict[str, Any]] = []
        used_targets: set[str] = set()
        used_comment_formats: set[str] = set()
        comment_texts: list[str] = []
        reply_limited = is_reply_limited(self._agent.agent_id)

        comment_budget = max(directive.target_comments, 0)
        if reply_limited:
            comment_budget = 0

        locked_posts: set[str] = set()
        if self._db_path and comment_budget > 0:
            locked_posts = await get_locked_post_ids(self._db_path, exclude_agent_id=self._agent.agent_id)

        comment_direction = ""
        if strategic_directive:
            comment_direction = strategic_directive.get("comment_direction", "")

        for index, post in enumerate(self._pick_comment_targets(context.feed_posts, comment_budget, locked_posts), start=1):
            used_targets.add(post.post_id)
            action = self._build_comment_action(
                post=post,
                directive=directive,
                used_formats=used_comment_formats,
                existing_texts=comment_texts,
                attempt_index=attempt_index,
                comment_index=index,
                hints=hints,
                comment_direction=comment_direction,
            )
            actions.append(action)
            used_comment_formats.add(str(action.get("editorial_format") or ""))
            if self._db_path:
                await lock_comment_target(self._db_path, agent_id=self._agent.agent_id, post_id=post.post_id)

        remaining_follows = max(directive.target_follows - sum(1 for action in actions if action.get("follow")), 0)
        if remaining_follows > 0:
            for post in context.feed_posts:
                if remaining_follows <= 0:
                    break
                if post.post_id in used_targets:
                    continue
                used_targets.add(post.post_id)
                actions.append(
                    {
                        "action": "follow",
                        "priority": 2,
                        "reason": "build graph without forcing repetitive text",
                        "target": post.post_id,
                        "target_author": post.author,
                    }
                )
                remaining_follows -= 1

        extra_likes = max(
            directive.target_likes - sum(1 for action in actions if action.get("action") == "comment" and action.get("like")),
            0,
        )
        for post in context.feed_posts:
            if extra_likes <= 0:
                break
            if post.post_id in used_targets:
                continue
            used_targets.add(post.post_id)
            actions.append(
                {
                    "action": "like",
                    "priority": 2,
                    "reason": "support adjacent thread without adding repetitive copy",
                    "target": post.post_id,
                    "target_author": post.author,
                }
            )
            extra_likes -= 1

        if directive.target_posts > 0:
            post_action = await self._build_post_action(
                context=context,
                directive=directive,
                recent_other_posts=recent_other_posts,
                recent_self_posts=history,
                audit_feedback=audit_feedback,
                attempt_index=attempt_index,
                strategic_directive=strategic_directive,
            )
            if post_action:
                actions.append(post_action)

        return AgentPlan(actions=actions)

    def _pick_comment_targets(self, feed_posts: list[Any], limit: int, exclude_post_ids: set[str] | None = None) -> list[Any]:
        if limit <= 0:
            return []
        excluded = exclude_post_ids or set()
        eligible = [post for post in feed_posts if post.post_id not in excluded]
        selected: list[Any] = []
        strong = [post for post in eligible if self._comment_target_tier(post) == 2]
        fallback = [post for post in eligible if self._comment_target_tier(post) == 1]
        self._append_comment_targets(selected=selected, candidates=strong, limit=limit)
        self._append_comment_targets(selected=selected, candidates=fallback, limit=limit)
        return selected

    def _append_comment_targets(self, *, selected: list[Any], candidates: list[Any], limit: int) -> None:
        seen_authors = {post.author for post in selected}
        seen_symbols = {
            symbol
            for post in selected
            for symbol in [self._extract_symbol(post.text)]
            if symbol
        }
        for post in candidates:
            if len(selected) >= limit:
                break
            symbol = self._extract_symbol(post.text)
            if post.author in seen_authors:
                continue
            if symbol and symbol in seen_symbols and len(selected) >= 2:
                continue
            selected.append(post)
            seen_authors.add(post.author)
            if symbol:
                seen_symbols.add(symbol)

    def _comment_target_tier(self, post: Any) -> int:
        reason = str(getattr(post, "selection_reason", "") or "")
        symbol = self._extract_symbol(post.text)
        domain = infer_comment_domain(post.text)
        policy = getattr(self._agent, "_policy", None)

        if policy and policy.comment_tier_rules:
            for rule in policy.comment_tier_rules:
                if rule.condition == "reason_any":
                    if any(v in reason for v in rule.values):
                        return rule.tier
                elif rule.condition == "symbol_not_major_and_market":
                    majors = set(rule.values)
                    if symbol and symbol not in majors and is_market_discussion(post.text):
                        return rule.tier
                elif rule.condition == "domain_in":
                    if domain in rule.values:
                        return rule.tier
                elif rule.condition == "symbol_and_market":
                    if symbol and is_market_discussion(post.text):
                        return rule.tier
            return 0

        # Fallback (no policy)
        if symbol and is_market_discussion(post.text):
            return 1
        return 0

    def _build_comment_action(
        self,
        *,
        post: Any,
        directive: Any,
        used_formats: set[str],
        existing_texts: list[str],
        attempt_index: int,
        comment_index: int,
        hints: RevisionHints,
        comment_direction: str = "",
    ) -> dict[str, Any]:
        action = {
            "action": "comment",
            "priority": 1,
            "reason": "join visible thread with an authored response",
            "target": post.post_id,
            "target_author": post.author,
            "target_text": post.text,
            "like": True,
            "follow": comment_index <= directive.target_follows,
            "editorial_angle": "authored",
            "editorial_format": "llm_authored",
        }
        if comment_direction:
            action["comment_direction"] = comment_direction
        return action

    async def _build_post_action(
        self,
        *,
        context: Any,
        directive: Any,
        recent_other_posts: list[dict[str, Any]],
        recent_self_posts: list[dict[str, Any]],
        audit_feedback: list[str] | None,
        attempt_index: int,
        strategic_directive: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        hints = self._build_revision_hints(
            audit_feedback=audit_feedback,
            recent_self_posts=recent_self_posts,
            recent_other_posts=recent_other_posts,
        )
        news_fingerprints: set[str] = set()
        if self._db_path:
            news_fingerprints = await get_active_news_fingerprints(self._db_path, exclude_agent_id=self._agent.agent_id)

        last_action: dict[str, Any] | None = None
        for variation in range(8):
            brief = self._editor.build_post_brief(
                context=context,
                directive=directive,
                recent_self_posts=recent_self_posts,
                recent_other_posts=recent_other_posts,
                audit_feedback=audit_feedback,
                attempt_index=attempt_index + variation,
                active_news_fingerprints=news_fingerprints,
                strategic_directive=strategic_directive,
            )
            if brief is None:
                continue
            action = self._render_post_action(
                brief,
                context=context,
                recent_self_posts=recent_self_posts,
                recent_other_posts=recent_other_posts,
                audit_feedback=audit_feedback,
                attempt_index=attempt_index + variation,
                strategic_directive=strategic_directive,
            )
            if not self._post_matches_revision_hints(action, hints):
                last_action = action
                continue
            if self._db_path:
                key = build_reservation_key(
                    coin=brief.primary_coin,
                    angle=brief.angle,
                    source_url=brief.source_url,
                    source_post_id=brief.source_post_id,
                )
                reserved = await reserve_topic(
                    self._db_path,
                    agent_id=self._agent.agent_id,
                    reservation_key=key,
                    post_family=brief.post_family,
                    primary_coin=brief.primary_coin,
                    angle=brief.angle,
                    source_fingerprint=brief.source_url or brief.source_post_id,
                )
                if not reserved:
                    last_action = action
                    continue
                action["reservation_key"] = key
            return action
        return last_action

    def _render_post_action(
        self,
        brief: Any,
        *,
        context: Any,
        recent_self_posts: list[dict[str, Any]],
        recent_other_posts: list[dict[str, Any]],
        audit_feedback: list[str] | None,
        attempt_index: int,
        strategic_directive: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        brief_context = self._serialize_brief(brief, context, strategic_directive=strategic_directive)
        action = {
            "action": "post",
            "priority": 3,
            "reason": f"publish a distinct {brief.post_family} take for {self._agent.agent_id}",
            "brief_context": brief_context,
            "source_kind": brief.source_kind,
            "source_post_id": brief.source_post_id,
            "source_url": brief.source_url,
            "editorial_angle": brief.angle,
            "editorial_format": brief.structure,
            "post_family": brief.post_family,
            "visual_kind": brief.visual_kind,
            "visual_title": brief.visual_title,
            "visual_subtitle": brief.visual_subtitle,
            "visual_context": brief.visual_context,
        }
        if brief.visual_kind == "chart_capture":
            # Only set chart_symbol/timeframe — visual_pipeline routes to screenshot_chart()
            # Do NOT set capture_url — that would route to capture_targeted_screenshot()
            # which produces a narrow header crop instead of a full chart
            action.update(
                {
                    "chart_symbol": brief.chart_symbol,
                    "chart_timeframe": brief.chart_timeframe,
                }
            )
        return action

    def _serialize_brief(
        self, brief: Any, context: Any, strategic_directive: dict[str, Any] | None = None,
    ) -> str:
        """Serialize editorial brief into readable context for the agent to write text."""
        lines = [
            f"post_family: {brief.post_family}",
            f"angle: {brief.angle}",
            f"structure: {brief.structure}",
            f"opening_mode: {brief.opening_mode}",
            f"primary_coin: {brief.primary_coin or 'none'}",
            f"source_kind: {brief.source_kind}",
        ]
        # Include strategic directive context for the author
        if strategic_directive:
            post_dir = strategic_directive.get("post_direction", "")
            tone = strategic_directive.get("tone", "")
            if post_dir:
                lines.append(f"strategic_direction: {post_dir}")
            if tone:
                lines.append(f"tone: {tone}")
        if brief.hook:
            lines.append(f"hook: {brief.hook}")
        if brief.context_line:
            lines.append(f"context_line: {brief.context_line}")
        if brief.insight_line:
            lines.append(f"insight_line: {brief.insight_line}")
        if brief.close_line:
            lines.append(f"close_line: {brief.close_line}")
        if brief.visual_title:
            lines.append(f"source_title: {brief.visual_title}")
        if brief.source_author:
            lines.append(f"source_author: {brief.source_author}")
        if brief.source_url:
            lines.append(f"source_url: {brief.source_url}")
        if brief.primary_coin and getattr(context, "market_data", None):
            market = context.market_data.get(brief.primary_coin, {})
            if isinstance(market, dict) and market:
                lines.append(f"live_market: {market}")
        return "\n".join(lines)

    def _build_revision_hints(
        self,
        *,
        audit_feedback: list[str] | None,
        recent_self_posts: list[dict[str, Any]],
        recent_other_posts: list[dict[str, Any]],
    ) -> RevisionHints:
        hints = RevisionHints(
            avoid_opening_signatures=self._collect_opening_signatures(recent_self_posts),
            avoid_coin_angle_pairs=self._collect_coin_angle_pairs(recent_self_posts),
            avoid_chart_symbols=self._collect_chart_symbols(recent_self_posts),
        )
        messages = " ".join(audit_feedback or []).lower()
        if "comment set is too internally repetitive" in messages:
            hints.force_comment_diversity = True
        if "same coin and angle" in messages:
            hints.avoid_coin_angle_pairs.update(self._collect_coin_angle_pairs(recent_other_posts))
        if "same chart visual" in messages or "same chart pair" in messages:
            hints.avoid_chart_symbols.update(self._collect_chart_symbols(recent_other_posts))
        return hints

    def _collect_opening_signatures(self, records: list[dict[str, Any]]) -> set[str]:
        return {
            str(record.get("opening_signature") or "").strip().lower()
            for record in records[:6]
            if str(record.get("opening_signature") or "").strip()
        }

    def _collect_coin_angle_pairs(self, records: list[dict[str, Any]]) -> set[tuple[str, str]]:
        pairs: set[tuple[str, str]] = set()
        for record in records[:6]:
            coin = str(record.get("primary_coin") or "").strip().upper()
            angle = str(record.get("angle") or "").strip().lower()
            if coin and angle:
                pairs.add((coin, angle))
        return pairs

    def _collect_chart_symbols(self, records: list[dict[str, Any]]) -> set[str]:
        return {
            str(record.get("chart_symbol") or "").strip().upper()
            for record in records[:6]
            if str(record.get("chart_symbol") or "").strip()
        }

    def _post_matches_revision_hints(self, action: dict[str, Any], hints: RevisionHints) -> bool:
        text = str(action.get("text") or "")
        if opening_signature(text) in hints.avoid_opening_signatures:
            return False

        coin = extract_primary_coin(text, chart_symbol=str(action.get("chart_symbol") or "") or None)
        angle = str(action.get("editorial_angle") or "").strip().lower()
        if coin and angle and (coin, angle) in hints.avoid_coin_angle_pairs:
            return False

        chart_symbol = str(action.get("chart_symbol") or "").strip().upper()
        if chart_symbol and chart_symbol in hints.avoid_chart_symbols:
            return False
        return True

    def _extract_symbol(self, text: str) -> str | None:
        match = re.search(r"\$([A-Z]{2,10})", text or "", re.IGNORECASE)
        if not match:
            return None
        return match.group(1).upper()
