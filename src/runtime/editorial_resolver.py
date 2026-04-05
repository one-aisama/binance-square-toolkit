"""Editorial resolver: template resolution, source selection, market formatting.

Extracted from editorial_brain.py to keep it under the 500-line limit.
EditorialBrain delegates template and source-selection calls here.
"""

from __future__ import annotations

from typing import Any

from src.runtime.content_fingerprint import add_cashtags, extract_primary_coin, normalize_text
from src.runtime.persona_policy import PersonaPolicy


class EditorialResolver:
    """Template resolution and source selection for editorial briefs."""

    def __init__(self, policy: PersonaPolicy | None):
        self._policy = policy

    # --- Template resolution ---

    def resolve_hook(self, family: str, opening_mode: str, **kwargs: Any) -> str:
        if not self._policy:
            return ""
        family_hooks = self._policy.hooks.get(family, {})
        template = family_hooks.get(opening_mode) or next(iter(family_hooks.values()), "")
        return self._render_template(template, **kwargs)

    def resolve_insight(self, family: str, *, angle: str = "", symbol: str | None = None, **kwargs: Any) -> str:
        if not self._policy:
            return ""
        family_insights = self._policy.insights.get(family, {})
        template = ""
        if family == "market_chart":
            source = kwargs.get("source", {})
            text = str(source.get("text") or "").lower() if isinstance(source, dict) else ""
            if angle in family_insights:
                template = family_insights[angle]
            elif any(kw in text for kw in ("etf", "powell", "fed")):
                template = family_insights.get("headline", "")
            else:
                template = family_insights.get("default", "")
        elif family == "news_reaction":
            title = str(kwargs.get("title", "")).lower()
            if any(kw in title for kw in ("listing", "launchpool", "airdrop")) and "listing" in family_insights:
                template = family_insights["listing"]
            elif symbol and "with_symbol" in family_insights:
                template = family_insights["with_symbol"]
            else:
                template = family_insights.get("default", "")
        elif family == "editorial_note":
            if symbol and "with_symbol" in family_insights:
                template = family_insights["with_symbol"]
            else:
                template = family_insights.get("default", "")
        return self._render_template(template, symbol=symbol, angle=angle, **kwargs)

    def resolve_close(self, family: str, *, angle: str = "", symbol: str | None = None, **kwargs: Any) -> str:
        if not self._policy:
            return ""
        family_closes = self._policy.closes.get(family, {})
        if angle in family_closes:
            template = family_closes[angle]
        elif symbol and "with_symbol" in family_closes:
            template = family_closes["with_symbol"]
        else:
            template = family_closes.get("default", "")
        return self._render_template(template, symbol=symbol, angle=angle, **kwargs)

    def resolve_context_line(self, family_key: str, *, offset: int = 0, **kwargs: Any) -> str:
        if self._policy and family_key in self._policy.context_line_templates:
            templates = self._policy.context_line_templates[family_key]
            if templates:
                template = templates[offset % len(templates)]
                return self._render_template(template, **kwargs)
        if family_key == "editorial":
            source_text = kwargs.get("source_text", "")
            author = kwargs.get("author", "")
            snippet = self.trim_text(source_text, 150)
            return f"the visible cue for that right now is @{author} pushing {snippet.lower()}"
        title = kwargs.get("title", "")
        source = kwargs.get("source", "news")
        headline = add_cashtags(self.trim_text(str(title), 140))
        return f"{headline} came through {source} and the wording is doing most of the emotional work on the timeline"

    def _render_template(self, template: str, **kwargs: Any) -> str:
        symbol = kwargs.get("symbol")
        coin = f"${symbol}" if symbol else ""
        coin_context = f" around ${symbol}" if symbol else ""
        source = kwargs.get("source", "")
        if isinstance(source, dict):
            source = str(source.get("author") or source.get("text", ""))
        title = kwargs.get("title", "")
        title_trimmed = add_cashtags(self.trim_text(str(title), 140))
        author = kwargs.get("author", "")
        source_text = kwargs.get("source_text", "")
        snippet = self.trim_text(str(source_text), 150).lower() if source_text else ""
        try:
            return template.format(
                coin=coin,
                coin_context=coin_context,
                symbol=symbol or "",
                source=source,
                title_trimmed=title_trimmed,
                author=author,
                snippet=snippet,
            )
        except (KeyError, IndexError):
            return template

    # --- Market formatting ---

    def market_snapshot(self, symbol: str, context: Any) -> str:
        market = context.market_data.get(symbol, {})
        price = float(market.get("price", 0.0) or 0.0)
        change = float(market.get("change_24h", 0.0) or 0.0)
        if price >= 1000:
            price_label = f"{price / 1000:.1f}K"
        elif price >= 1:
            price_label = f"{price:.2f}"
        else:
            price_label = f"{price:.4f}"
        return f"{symbol} is trading near {price_label} with a {change:+.1f}% day"

    def market_visual_subtitle(self, *, symbol: str, source: dict[str, str | None]) -> str:
        if source.get("kind") == "feed":
            return f"Feed context from @{source.get('author') or 'market'}"
        if source.get("kind") == "news":
            return f"Headline context from {source.get('author') or 'news'}"
        return f"Live market read on {symbol}"

    # --- News item selection ---

    def select_news_item(
        self, items: list[dict[str, Any]], directive: Any,
        recent_self_posts: list[dict[str, Any]], recent_other_posts: list[dict[str, Any]],
        active_news_fingerprints: set[str] | None = None,
    ) -> dict[str, Any] | None:
        if not items:
            return None
        preferred_symbols = [str(symbol).upper() for symbol in getattr(directive, "preferred_symbols", [])]
        cooldown_penalty = 300.0
        if self._policy:
            cooldown_penalty = self._policy.runtime_tuning.scoring.news_cooldown_penalty
        ranked: list[tuple[float, dict[str, Any]]] = []
        for item in items:
            title = str(item.get("title", ""))
            lowered = title.lower()
            score = 0.0
            if any(symbol in title.upper() for symbol in preferred_symbols):
                score += 50.0
            if self._policy:
                for keyword, bonus in self._policy.news_keyword_affinity.items():
                    if keyword in lowered:
                        score += bonus
            score -= self._news_overlap_penalty(item, recent_self_posts)
            score -= self._news_overlap_penalty(item, recent_other_posts)
            if active_news_fingerprints:
                from src.runtime.news_cooldown import _news_fingerprint
                fp = _news_fingerprint(str(item.get("url") or ""), title)
                if fp in active_news_fingerprints:
                    score -= cooldown_penalty
            ranked.append((score, item))
        ranked.sort(key=lambda item: item[0], reverse=True)
        if ranked and ranked[0][0] <= -200.0:
            return None
        return ranked[0][1]

    def _news_overlap_penalty(self, item: dict[str, Any], recent_posts: list[dict[str, Any]]) -> float:
        scoring = self._policy.runtime_tuning.scoring if self._policy else None
        url_penalty = scoring.news_url_overlap_penalty if scoring else 500.0
        title_penalty = scoring.news_title_overlap_penalty if scoring else 450.0
        title = normalize_text(str(item.get("title", "")))
        source_url = str(item.get("url", "") or "")
        penalty = 0.0
        for index, record in enumerate(recent_posts[:8], start=1):
            if source_url and str(record.get("source_url", "") or "") == source_url:
                penalty += url_penalty / index
                continue
            recent_title = normalize_text(str(record.get("source_title", "") or ""))
            if title and recent_title and title == recent_title:
                penalty += title_penalty / index
        return penalty

    # --- Editorial source selection ---

    def select_editorial_source_post(
        self, feed_posts: list[Any],
        recent_self_posts: list[dict[str, Any]], recent_other_posts: list[dict[str, Any]],
    ) -> Any | None:
        if not feed_posts:
            return None
        ranked: list[tuple[float, Any]] = []
        for index, post in enumerate(feed_posts):
            score = float(max(0, 120 - index * 10))
            score -= self._feed_source_overlap_penalty(post.post_id, recent_self_posts)
            score -= self._feed_source_overlap_penalty(post.post_id, recent_other_posts)
            ranked.append((score, post))
        ranked.sort(key=lambda item: item[0], reverse=True)
        if ranked and ranked[0][0] <= -120.0:
            return None
        return ranked[0][1]

    def _feed_source_overlap_penalty(self, post_id: str, recent_posts: list[dict[str, Any]]) -> float:
        scoring = self._policy.runtime_tuning.scoring if self._policy else None
        base = scoring.feed_source_overlap_penalty if scoring else 300.0
        penalty = 0.0
        for index, record in enumerate(recent_posts[:8], start=1):
            if str(record.get("source_post_id", "") or "") == str(post_id):
                penalty += base / index
        return penalty

    # --- Utilities ---

    def extract_symbol_from_text(self, text: str, candidates: Any) -> str | None:
        upper_text = str(text or "").upper()
        for symbol in candidates:
            token = str(symbol).upper()
            if token and token in upper_text:
                return token
        return extract_primary_coin(text)

    def trim_text(self, text: str, limit: int) -> str:
        cleaned = " ".join(str(text or "").split())
        if len(cleaned) <= limit:
            return cleaned
        return cleaned[: limit - 1].rstrip() + "\u2026"
