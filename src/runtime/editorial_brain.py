from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.runtime.content_fingerprint import extract_primary_coin, infer_angle
from src.runtime.editorial_resolver import EditorialResolver
from src.runtime.persona_policy import PersonaPolicy


@dataclass(frozen=True)
class EditorialBrief:
    post_family: str
    visual_kind: str
    primary_coin: str | None
    chart_symbol: str | None
    chart_timeframe: str | None
    angle: str
    structure: str
    opening_mode: str
    hook: str
    context_line: str
    insight_line: str
    close_line: str
    visual_title: str
    visual_subtitle: str
    visual_context: str
    source_kind: str
    source_post_id: str | None = None
    source_author: str | None = None
    source_url: str | None = None


class EditorialBrain:
    def __init__(self, *, agent: Any, policy: PersonaPolicy | None = None):
        self._agent = agent
        self._policy = policy
        self._resolver = EditorialResolver(policy)

    def build_post_brief(
        self,
        *,
        context: Any,
        directive: Any,
        recent_self_posts: list[dict[str, Any]],
        recent_other_posts: list[dict[str, Any]],
        audit_feedback: list[str] | None = None,
        attempt_index: int = 0,
        active_news_fingerprints: set[str] | None = None,
        strategic_directive: dict[str, Any] | None = None,
    ) -> EditorialBrief | None:
        family = self._choose_post_family(
            context, directive, recent_self_posts, attempt_index,
            strategic_directive=strategic_directive,
        )
        if family == "news_reaction":
            brief = self._build_news_brief(
                context, directive, recent_self_posts, recent_other_posts, attempt_index,
                active_news_fingerprints=active_news_fingerprints,
            )
            if brief:
                return brief
        if family == "editorial_note":
            brief = self._build_editorial_brief(
                context, directive, recent_self_posts, recent_other_posts, attempt_index,
            )
            if brief:
                return brief
        return self._build_market_brief(
            context, directive, recent_self_posts, attempt_index,
            strategic_directive=strategic_directive,
        )

    # --- Post family selection ---

    def _choose_post_family(
        self, context: Any, directive: Any, recent_self_posts: list[dict[str, Any]], attempt_index: int,
        strategic_directive: dict[str, Any] | None = None,
    ) -> str:
        recent_families = [str(record.get("post_family") or "") for record in recent_self_posts[:3]]
        family_scores: list[tuple[float, str]] = []

        market_score = 140.0 if context.market_data else -100.0
        news_score = 130.0 if context.news else -100.0
        editorial_score = 120.0 if context.feed_posts else -100.0

        if self._policy:
            adj = self._policy.family_score_adjustments
            market_score += adj.get("market", 0.0)
            news_score += adj.get("news", 0.0)
            editorial_score += adj.get("editorial", 0.0)

        if getattr(directive, "stage", "") == "post_only_validation":
            news_score += 20.0
            editorial_score += 20.0
        else:
            market_score += 80.0

        # Strategic directive: skip_families penalty
        skip_families = set()
        if strategic_directive:
            skip_families = {f.lower() for f in strategic_directive.get("skip_families", [])}

        for family, base_score in {
            "market_chart": market_score,
            "news_reaction": news_score,
            "editorial_note": editorial_score,
        }.items():
            score = base_score
            if family in recent_families:
                rep_penalty = self._policy.runtime_tuning.scoring.family_repetition_penalty if self._policy else 60.0
                score -= rep_penalty * (recent_families.index(family) + 1)
            if family in skip_families:
                score -= 500.0
            family_scores.append((score, family))

        family_scores.sort(key=lambda item: item[0], reverse=True)
        offset = max(attempt_index, 0)
        return family_scores[offset % len(family_scores)][1]

    # --- Market brief ---

    def _build_market_brief(
        self, context: Any, directive: Any, recent_self_posts: list[dict[str, Any]], attempt_index: int,
        strategic_directive: dict[str, Any] | None = None,
    ) -> EditorialBrief | None:
        candidates = self._candidate_symbols(context, directive, strategic_directive=strategic_directive)
        if not candidates:
            return None
        ranked = [
            self._score_symbol(
                symbol=symbol, context=context, recent_self_posts=recent_self_posts,
                strategic_directive=strategic_directive,
            )
            for symbol in candidates
        ]
        ranked = [item for item in ranked if item[0] > -500]
        if not ranked:
            return None
        ranked.sort(key=lambda item: item[0], reverse=True)
        offset = max(attempt_index, 0)
        symbol = ranked[offset % len(ranked)][1]
        source = self._select_market_source(symbol, context)
        angle = self._choose_market_angle(symbol=symbol, source=source, context=context)
        structure = self._choose_structure("market_chart", recent_self_posts, offset)
        opening_mode = self._choose_opening("market_chart", recent_self_posts, offset)
        timeframe = self._select_timeframe(symbol)
        snapshot = self._market_snapshot(symbol, context)
        return EditorialBrief(
            post_family="market_chart",
            visual_kind="chart_capture",
            primary_coin=symbol,
            chart_symbol=f"{symbol}_USDT",
            chart_timeframe=timeframe,
            angle=angle,
            structure=structure,
            opening_mode=opening_mode,
            hook=self._resolve_hook("market_chart", opening_mode, symbol=symbol),
            context_line=snapshot,
            insight_line=self._resolve_insight("market_chart", angle=angle, symbol=symbol, source=source),
            close_line=self._resolve_close("market_chart", angle=angle, symbol=symbol),
            visual_title=f"{symbol}/USDT {timeframe}",
            visual_subtitle=self._market_visual_subtitle(symbol=symbol, source=source),
            visual_context=snapshot,
            source_kind=source["kind"],
            source_post_id=source.get("post_id"),
            source_author=source.get("author"),
        )

    # --- News brief ---

    def _build_news_brief(
        self, context: Any, directive: Any,
        recent_self_posts: list[dict[str, Any]], recent_other_posts: list[dict[str, Any]],
        attempt_index: int,
        active_news_fingerprints: set[str] | None = None,
    ) -> EditorialBrief | None:
        item = self._select_news_item(context.news, directive, recent_self_posts, recent_other_posts,
                                       active_news_fingerprints=active_news_fingerprints)
        if item is None:
            return None
        title = str(item.get("title", "")).strip()
        symbol = self._extract_symbol_from_text(title, context.market_data.keys())
        if self._policy and symbol in self._policy.coin_bias.exclude_from_posts:
            symbol = None
        angle = infer_angle(title)
        if angle == "general" and self._policy:
            angle = self._policy.default_news_angle
        structure = self._choose_structure("news_reaction", recent_self_posts, max(attempt_index, 0))
        opening_mode = self._choose_opening("news_reaction", recent_self_posts, max(attempt_index, 0))
        source = str(item.get("source", "news"))
        context_line = self._resolve_context_line("news", title=title, source=source, offset=attempt_index)
        return EditorialBrief(
            post_family="news_reaction",
            visual_kind="news_card",
            primary_coin=symbol,
            chart_symbol=None,
            chart_timeframe=None,
            angle=angle,
            structure=structure,
            opening_mode=opening_mode,
            hook=self._resolve_hook("news_reaction", opening_mode, symbol=symbol, source=source),
            context_line=context_line,
            insight_line=self._resolve_insight("news_reaction", angle=angle, symbol=symbol, title=title),
            close_line=self._resolve_close("news_reaction", symbol=symbol, source=source),
            visual_title=title,
            visual_subtitle=source,
            visual_context=context_line,
            source_kind="news",
            source_author=source,
            source_url=str(item.get("url", "") or "") or None,
        )

    # --- Editorial brief ---

    def _build_editorial_brief(
        self, context: Any, directive: Any,
        recent_self_posts: list[dict[str, Any]], recent_other_posts: list[dict[str, Any]],
        attempt_index: int,
    ) -> EditorialBrief | None:
        post = self._select_editorial_source_post(context.feed_posts, recent_self_posts, recent_other_posts)
        if post is None:
            return None
        source_text = str(post.text or "")
        symbol = extract_primary_coin(source_text)
        if self._policy and symbol in self._policy.coin_bias.exclude_from_posts:
            symbol = None
        angle = infer_angle(source_text)
        if angle == "general" and self._policy:
            angle = self._policy.default_editorial_angle
        structure = self._choose_structure("editorial_note", recent_self_posts, max(attempt_index, 0))
        opening_mode = self._choose_opening("editorial_note", recent_self_posts, max(attempt_index, 0))
        context_line = self._resolve_context_line("editorial", source_text=source_text, author=post.author)
        return EditorialBrief(
            post_family="editorial_note",
            visual_kind="reaction_card",
            primary_coin=symbol,
            chart_symbol=None,
            chart_timeframe=None,
            angle=angle,
            structure=structure,
            opening_mode=opening_mode,
            hook=self._resolve_hook("editorial_note", opening_mode, symbol=symbol),
            context_line=context_line,
            insight_line=self._resolve_insight("editorial_note", symbol=symbol, source_text=source_text),
            close_line=self._resolve_close("editorial_note", symbol=symbol),
            visual_title=self._trim_text(source_text, 90),
            visual_subtitle=f"Feed note from @{post.author}",
            visual_context=self._trim_text(source_text, 130),
            source_kind="feed",
            source_post_id=post.post_id,
            source_author=post.author,
        )

    # --- Symbol selection ---

    def _candidate_symbols(
        self, context: Any, directive: Any, strategic_directive: dict[str, Any] | None = None,
    ) -> list[str]:
        preferred = [str(symbol).upper() for symbol in getattr(directive, "preferred_symbols", [])]
        candidates = preferred or [str(symbol).upper() for symbol in context.market_data.keys()]
        if self._policy:
            exclude = set(self._policy.coin_bias.exclude_from_posts)
            candidates = [s for s in candidates if s not in exclude]
        # Strategic directive: filter out avoid_coins
        if strategic_directive:
            avoid = {c.upper() for c in strategic_directive.get("avoid_coins", [])}
            candidates = [s for s in candidates if s not in avoid]
            # Prepend preferred_coins from directive (if not already in list)
            strat_preferred = [c.upper() for c in strategic_directive.get("preferred_coins", [])]
            if strat_preferred:
                existing = set(candidates)
                front = [c for c in strat_preferred if c in existing]
                rest = [c for c in candidates if c not in set(strat_preferred)]
                candidates = front + rest
        return list(dict.fromkeys(candidates))

    def _score_symbol(
        self, *, symbol: str, context: Any, recent_self_posts: list[dict[str, Any]],
        strategic_directive: dict[str, Any] | None = None,
    ) -> tuple[float, str]:
        market = context.market_data.get(symbol, {})
        if not isinstance(market, dict):
            return -1000.0, symbol
        score = abs(float(market.get("change_24h", 0.0) or 0.0)) * 12
        score += self._agent_bias(symbol)
        score += self._source_bonus(symbol, context)
        score -= self._self_overlap_penalty(symbol, recent_self_posts)
        # Strategic directive bonus for preferred coins
        if strategic_directive:
            preferred = {c.upper() for c in strategic_directive.get("preferred_coins", [])}
            if symbol in preferred:
                score += 80.0
        return score, symbol

    def _agent_bias(self, symbol: str) -> float:
        if not self._policy:
            return 0.0
        bias = self._policy.coin_bias
        if symbol in bias.preferred:
            return bias.preferred_bonus
        if symbol in bias.exclude_from_posts and bias.excluded_penalty != 0.0:
            return bias.excluded_penalty
        return bias.other_bonus

    def _source_bonus(self, symbol: str, context: Any) -> float:
        scoring = self._policy.runtime_tuning.scoring if self._policy else None
        feed_match = 55.0
        feed_keyword = 20.0
        news_match = 35.0
        # Scoring overrides are not per-bonus but the structure is ready for YAML extension
        bonus = 0.0
        for post in context.feed_posts[:12]:
            if extract_primary_coin(post.text or "") == symbol:
                bonus += feed_match
                if "rotation" in (post.selection_reason or ""):
                    bonus += feed_keyword
                if "macro" in (post.selection_reason or ""):
                    bonus += feed_keyword
        for item in context.news[:4]:
            title = str(item.get("title", ""))
            if symbol in title.upper():
                bonus += news_match
        return bonus

    def _self_overlap_penalty(self, symbol: str, recent_self_posts: list[dict[str, Any]]) -> float:
        scoring = self._policy.runtime_tuning.scoring if self._policy else None
        base = scoring.symbol_self_overlap_penalty if scoring else 220.0
        penalty = 0.0
        for index, record in enumerate(recent_self_posts[:6], start=1):
            if str(record.get("primary_coin") or "").upper() != symbol:
                continue
            penalty += base / index
        return penalty

    def _select_market_source(self, symbol: str, context: Any) -> dict[str, str | None]:
        for post in context.feed_posts[:12]:
            if extract_primary_coin(post.text or "") != symbol:
                continue
            return {"kind": "feed", "post_id": post.post_id, "author": post.author, "text": post.text}
        for item in context.news[:4]:
            title = str(item.get("title", ""))
            if symbol in title.upper():
                return {"kind": "news", "post_id": None, "author": str(item.get("source", "news")), "text": title}
        return {"kind": "market", "post_id": None, "author": None, "text": ""}

    def _choose_market_angle(self, *, symbol: str, source: dict[str, str | None], context: Any) -> str:
        source_text = str(source.get("text") or "")
        source_angle = infer_angle(source_text)
        if source_angle != "general":
            return source_angle
        market = context.market_data.get(symbol, {})
        change = abs(float(market.get("change_24h", 0.0) or 0.0))
        if self._policy:
            rules = self._policy.market_angle_rules
            if change >= rules.high_change_threshold:
                return rules.high_change_angle
            if symbol in rules.major_coins:
                return rules.major_coins_angle
            return rules.low_change_angle
        return "macro"

    # --- Structure and opening selection ---

    def _choose_structure(self, post_family: str, recent_self_posts: list[dict[str, Any]], offset: int) -> str:
        options = self._structure_options(post_family)
        recent = [str(record.get("editorial_format") or "") for record in recent_self_posts[:3]]
        fresh = [option for option in options if option not in recent]
        pool = fresh or options
        return pool[offset % len(pool)]

    def _choose_opening(self, post_family: str, recent_self_posts: list[dict[str, Any]], offset: int) -> str:
        options = self._opening_options(post_family)
        recent = [str(record.get("opening_signature") or "") for record in recent_self_posts[:3]]
        pool = [option for option in options if option not in recent] or options
        return pool[offset % len(pool)]

    def _structure_options(self, post_family: str) -> list[str]:
        if self._policy and post_family in self._policy.structures:
            return self._policy.structures[post_family]
        return ["observation", "contrast", "filter", "process"]

    def _opening_options(self, post_family: str) -> list[str]:
        if self._policy and post_family in self._policy.openings:
            return self._policy.openings[post_family]
        return ["screen_vs_tape", "slow_down", "what_matters", "not_calling_it"]

    # --- Timeframe ---

    def _select_timeframe(self, symbol: str) -> str:
        if self._policy:
            override = self._policy.timeframe_overrides.get(symbol)
            if override:
                return override
            return self._policy.default_chart_timeframe
        return "1D"

    # --- Delegated to EditorialResolver ---

    def _resolve_hook(self, family: str, opening_mode: str, **kwargs: Any) -> str:
        return self._resolver.resolve_hook(family, opening_mode, **kwargs)

    def _resolve_insight(self, family: str, *, angle: str = "", symbol: str | None = None, **kwargs: Any) -> str:
        return self._resolver.resolve_insight(family, angle=angle, symbol=symbol, **kwargs)

    def _resolve_close(self, family: str, *, angle: str = "", symbol: str | None = None, **kwargs: Any) -> str:
        return self._resolver.resolve_close(family, angle=angle, symbol=symbol, **kwargs)

    def _resolve_context_line(self, family_key: str, *, offset: int = 0, **kwargs: Any) -> str:
        return self._resolver.resolve_context_line(family_key, offset=offset, **kwargs)

    def _market_snapshot(self, symbol: str, context: Any) -> str:
        return self._resolver.market_snapshot(symbol, context)

    def _market_visual_subtitle(self, *, symbol: str, source: dict[str, str | None]) -> str:
        return self._resolver.market_visual_subtitle(symbol=symbol, source=source)

    def _select_news_item(
        self, items: list[dict[str, Any]], directive: Any,
        recent_self_posts: list[dict[str, Any]], recent_other_posts: list[dict[str, Any]],
        active_news_fingerprints: set[str] | None = None,
    ) -> dict[str, Any] | None:
        return self._resolver.select_news_item(
            items, directive, recent_self_posts, recent_other_posts, active_news_fingerprints,
        )

    def _select_editorial_source_post(
        self, feed_posts: list[Any],
        recent_self_posts: list[dict[str, Any]], recent_other_posts: list[dict[str, Any]],
    ) -> Any | None:
        return self._resolver.select_editorial_source_post(feed_posts, recent_self_posts, recent_other_posts)

    def _extract_symbol_from_text(self, text: str, candidates: Any) -> str | None:
        return self._resolver.extract_symbol_from_text(text, candidates)

    def _trim_text(self, text: str, limit: int) -> str:
        return self._resolver.trim_text(text, limit)
