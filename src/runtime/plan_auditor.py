from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from src.runtime.agent_plan import AgentPlan
from src.runtime.content_fingerprint import (
    extract_primary_coin,
    format_signature,
    infer_angle,
    normalize_text,
    opening_signature,
    similarity_ratio,
    visual_type_from_action,
)
from src.runtime.media_policy import is_image_visual, should_attach_image
from src.runtime.topic_reservation import build_reservation_key


@dataclass
class AuditIssue:
    """Single blocking issue found during plan audit."""

    message: str


@dataclass
class AuditResult:
    """Audit result for a generated plan."""

    issues: list[AuditIssue] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return len(self.issues) == 0

    def messages(self) -> list[str]:
        return [issue.message for issue in self.issues]


class PlanAuditor:
    """Deterministic guardrail layer before executing an autonomous plan."""

    def audit(
        self,
        plan: AgentPlan,
        *,
        agent: Any,
        context: Any,
        directive: Any,
        recent_other_posts: list[dict[str, Any]],
        recent_self_posts: list[dict[str, Any]] | None = None,
        active_reservations: list[dict[str, str | None]] | None = None,
    ) -> AuditResult:
        del context
        issues: list[AuditIssue] = []
        actions = plan.sorted_actions()
        own_history = list(recent_self_posts or [])

        issues.extend(self._audit_stage_rules(actions, agent, directive))
        issues.extend(self._audit_text_rules(actions))
        issues.extend(self._audit_comment_diversity(actions, agent))
        issues.extend(self._audit_agent_style(actions, agent))
        issues.extend(self._audit_media_policy(actions, agent))
        issues.extend(self._audit_self_novelty(actions, own_history, agent))
        issues.extend(self._audit_overlap(actions, recent_other_posts, agent))
        issues.extend(self._audit_reservation_conflicts(actions, active_reservations or []))
        issues.extend(self._audit_territory_drift(actions, agent))

        return AuditResult(issues=issues)

    def _audit_stage_rules(self, actions: list[Any], agent: Any, directive: Any) -> list[AuditIssue]:
        issues: list[AuditIssue] = []
        comments = sum(1 for action in actions if action.action == "comment")
        posts = sum(1 for action in actions if action.action == "post")
        follows = sum(1 for action in actions if action.action == "follow") + sum(
            1 for action in actions if action.action == "comment" and action.follow
        )
        likes = sum(1 for action in actions if action.action == "like")

        if directive.stage == "post_only_validation":
            if any(action.action != "post" for action in actions):
                issues.append(AuditIssue("Post-only validation plans must not include likes, follows, or comments"))
            if posts != directive.target_posts:
                issues.append(AuditIssue("Post-only validation plans must publish exactly one original post per slot"))
            return issues

        policy = getattr(agent, "_policy", None)
        if policy and directive.stage in policy.audit_style.stage_rules:
            rules = policy.audit_style.stage_rules[directive.stage]
            for rule in rules:
                if "require at least one follow" in rule and follows < 1:
                    issues.append(AuditIssue(f"{directive.stage}: must include at least one follow action"))
                if "max one post" in rule and posts > 1:
                    issues.append(AuditIssue(f"{directive.stage}: must not publish more than one post per cycle"))
                if "need at least three comments" in rule and comments < 3:
                    issues.append(AuditIssue(f"{directive.stage}: need at least three comments before posting"))
                if "zero comments allowed" in rule and comments > 0:
                    issues.append(AuditIssue(f"{directive.stage}: must avoid reply actions until cooldown expires"))
                if "require visible non-post activity" in rule and likes + follows < 1:
                    issues.append(AuditIssue(f"{directive.stage}: should include visible non-post activity"))
        return issues

    def _audit_text_rules(self, actions: list[Any]) -> list[AuditIssue]:
        issues: list[AuditIssue] = []
        for action in actions:
            if action.action not in {"post", "comment", "quote_repost"}:
                continue
            text = (action.text or "").strip()
            if not text:
                continue
            if text.endswith("."):
                issues.append(AuditIssue(f"{action.action} text must not end with a trailing period"))
            paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
            for paragraph in paragraphs:
                if paragraph.endswith("."):
                    issues.append(AuditIssue(f"{action.action} paragraphs must not end with a trailing period"))
                    break
        return issues

    def _get_thresholds(self, agent: Any) -> Any:
        policy = getattr(agent, "_policy", None)
        if policy:
            return policy.runtime_tuning.similarity
        from src.runtime.persona_policy import SimilarityThresholds
        return SimilarityThresholds()

    def _audit_comment_diversity(self, actions: list[Any], agent: Any = None) -> list[AuditIssue]:
        thresholds = self._get_thresholds(agent)
        comments = [action for action in actions if action.action == "comment" and (action.text or "").strip()]
        if len(comments) < 2:
            return []
        issues: list[AuditIssue] = []
        for index, action in enumerate(comments):
            for other in comments[index + 1:]:
                if similarity_ratio(action.text or "", other.text or "") >= thresholds.comment_diversity:
                    issues.append(AuditIssue("Comment set is too internally repetitive for one cycle"))
                    return issues
        return issues

    def _audit_agent_style(self, actions: list[Any], agent: Any) -> list[AuditIssue]:
        issues: list[AuditIssue] = []
        policy = getattr(agent, "_policy", None)
        for action in actions:
            if action.action != "post":
                continue
            text = (action.text or "").strip()
            primary_coin = self._primary_coin(action)
            family = str(action.post_family or "market_chart")

            if policy:
                style = policy.audit_style
                # Text checks only when agent has already written text
                if text:
                    if len(text) < style.min_post_length:
                        issues.append(AuditIssue("Post is too short for this persona's style requirements"))
                    paragraphs = [part for part in re.split(r"\n\s*\n", text) if part.strip()]
                    if style.min_paragraphs_market > 0 and family == "market_chart" and len(paragraphs) < style.min_paragraphs_market:
                        issues.append(AuditIssue("Market posts should keep at least two clear paragraphs"))
                # Metadata checks always apply
                if family == "market_chart" and primary_coin in style.reject_coins_for_market:
                    issues.append(AuditIssue(f"Market posts must not focus on {primary_coin} for this persona"))
        return issues

    def _audit_media_policy(self, actions: list[Any], agent: Any) -> list[AuditIssue]:
        if not should_attach_image(agent.agent_id):
            return []

        issues: list[AuditIssue] = []
        for action in actions:
            if action.action != "post":
                continue
            if not is_image_visual(self._visual_type(action)):
                issues.append(AuditIssue("Media policy requires an attached image on every post"))
        return issues

    def _audit_self_novelty(self, actions: list[Any], recent_self_posts: list[dict[str, Any]], agent: Any = None) -> list[AuditIssue]:
        thresholds = self._get_thresholds(agent)
        issues: list[AuditIssue] = []
        for action in actions:
            if action.action != "post":
                continue
            current_coin = self._primary_coin(action)
            current_angle = action.editorial_angle or infer_angle(action.text or "")
            current_opening = opening_signature(action.text or "")
            current_format = action.editorial_format or format_signature(action.text or "")
            current_text = action.text or ""
            current_chart = action.chart_symbol or ""
            current_family = str(action.post_family or "")
            current_visual = self._visual_type(action)

            for record in recent_self_posts[:6]:
                if current_text and similarity_ratio(current_text, str(record.get("text") or "")) >= thresholds.self_novelty_text:
                    issues.append(AuditIssue("Planned post is too similar to the agent's own recent post"))
                    break
                if current_opening and record.get("opening_signature") == current_opening:
                    issues.append(AuditIssue("Planned post reuses the same opening pattern from the agent's recent post"))
                    break
                if current_format and record.get("editorial_format") == current_format:
                    issues.append(AuditIssue("Planned post reuses the same structural format from the recent window"))
                    break
                if current_chart and record.get("chart_symbol") == current_chart:
                    issues.append(AuditIssue("Planned post reuses the same chart pair from the recent window"))
                    break
                if current_coin and record.get("primary_coin") == current_coin and record.get("angle") == current_angle:
                    issues.append(AuditIssue("Planned post repeats the same coin and angle from the agent's recent window"))
                    break
                if current_family and record.get("post_family") == current_family and record.get("visual_kind") == current_visual:
                    same_coin = bool(current_coin and record.get("primary_coin") == current_coin)
                    similar_text = similarity_ratio(current_text, str(record.get("text") or "")) >= thresholds.self_novelty_relaxed
                    same_opening = bool(current_opening and record.get("opening_signature") == current_opening)
                    if same_coin or similar_text or same_opening:
                        issues.append(AuditIssue("Planned post repeats the same post family and visual pattern from the recent window"))
                        break
        return issues

    def _audit_overlap(self, actions: list[Any], recent_other_posts: list[dict[str, Any]], agent: Any = None) -> list[AuditIssue]:
        thresholds = self._get_thresholds(agent)
        issues: list[AuditIssue] = []
        for action in actions:
            if action.action != "post":
                continue
            current_coin = self._primary_coin(action)
            current_visual = self._visual_type(action)
            current_chart = action.chart_symbol or ""
            current_angle = action.editorial_angle or infer_angle(action.text or "")
            current_normalized = normalize_text(action.text or "")
            current_family = str(action.post_family or "")
            current_source_url = str(action.source_url or "")
            current_source_post_id = str(action.source_post_id or "")

            for record in recent_other_posts:
                same_visual = record.get("visual_type") == current_visual
                same_chart = bool(current_chart and record.get("chart_symbol") == current_chart)
                same_coin = bool(current_coin and record.get("primary_coin") == current_coin)
                same_angle = record.get("angle") == current_angle
                same_family = bool(current_family and record.get("post_family") == current_family)
                same_source_url = bool(current_source_url and record.get("source_url") == current_source_url)
                same_source_post = bool(current_source_post_id and record.get("source_post_id") == current_source_post_id)
                similarity = SequenceMatcher(None, current_normalized, record.get("normalized_text", "")).ratio()

                if same_source_url:
                    issues.append(AuditIssue("Planned post reuses the same news source another agent used recently"))
                    break
                if same_source_post:
                    issues.append(AuditIssue("Planned post reuses the same feed source another agent used recently"))
                    break
                if same_chart and same_visual:
                    issues.append(AuditIssue("Planned post reuses the same chart visual another agent used recently"))
                    break
                if same_coin and same_angle:
                    issues.append(AuditIssue("Planned post overlaps another agent on the same coin and angle from the recent window"))
                    break
                if current_normalized and same_family and same_visual and similarity >= thresholds.feed_novelty_format:
                    issues.append(AuditIssue("Planned post is too visually and structurally close to another agent's recent post"))
                    break
                if current_normalized and same_coin and similarity >= thresholds.feed_novelty_coin:
                    issues.append(AuditIssue("Planned post is too textually similar to another agent's recent post"))
                    break
        return issues

    def _audit_reservation_conflicts(
        self, actions: list[Any], active_reservations: list[dict[str, str | None]],
    ) -> list[AuditIssue]:
        if not active_reservations:
            return []
        issues: list[AuditIssue] = []
        reserved_keys = {str(r.get("reservation_key") or "") for r in active_reservations}
        for action in actions:
            if action.action != "post":
                continue
            coin = self._primary_coin(action)
            angle = action.editorial_angle or infer_angle(action.text or "")
            key = build_reservation_key(
                coin=coin,
                angle=angle,
                source_url=str(action.source_url or "") or None,
                source_post_id=str(action.source_post_id or "") or None,
            )
            if key in reserved_keys:
                issues.append(AuditIssue("Planned post topic is already reserved by another agent"))
                break
        return issues

    def _audit_territory_drift(self, actions: list[Any], agent: Any) -> list[AuditIssue]:
        """Soft check: reject if ALL posts are off the agent's preferred territory."""
        policy = getattr(agent, "_policy", None)
        if not policy or not policy.coin_bias.preferred:
            return []
        post_actions = [a for a in actions if a.action == "post"]
        if len(post_actions) < 2:
            return []
        preferred = set(c.upper() for c in policy.coin_bias.preferred)
        on_territory = sum(
            1 for a in post_actions
            if (self._primary_coin(a) or "").upper() in preferred
        )
        if on_territory == 0:
            return [AuditIssue("All planned posts are outside the agent's preferred territory")]
        return []

    def _primary_coin(self, action: Any) -> str | None:
        return extract_primary_coin(action.text or "", coin=action.coin, chart_symbol=action.chart_symbol)

    def _visual_type(self, action: Any) -> str:
        return visual_type_from_action(action)



