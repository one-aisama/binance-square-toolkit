"""ActionScorer — aggregates outcomes into insights.

First 30 sessions: no weights, just raw averages per dimension.
Generates automatic lessons when patterns emerge (sample_count >= 3).
"""

import logging
from collections import defaultdict
from datetime import datetime
from typing import Any

import aiosqlite

from src.metrics.store import MetricsStore

logger = logging.getLogger("bsq.metrics.scorer")

DIMENSIONS = ("author", "content_type", "hour", "topic", "has_image")

# SQL query joining actions with collected outcomes
_ACTIONS_WITH_OUTCOMES_SQL = """
SELECT
    a.id,
    a.agent_id,
    a.action_type,
    a.target_id,
    a.target_author,
    a.topic,
    a.content_type,
    a.has_image,
    a.timestamp_utc,
    o.views,
    o.likes,
    o.comments,
    o.quotes,
    o.author_replied,
    o.other_replies
FROM agent_actions a
JOIN outcomes o ON a.id = o.action_id
WHERE a.agent_id = ?
  AND o.status = 'collected'
ORDER BY a.timestamp_utc
"""


class ActionScorer:
    """Aggregates collected outcomes into insights by dimension.

    No hardcoded weights — just raw averages. Weights are deferred
    to a future version (configurable via settings.yaml).
    """

    def __init__(self, store: MetricsStore):
        self._store = store

    async def score_all(self, agent_id: str) -> dict[str, int]:
        """Aggregate all outcomes into insights and generate lessons.

        Args:
            agent_id: Agent identifier.

        Returns:
            {"dimensions_updated": N, "lessons_generated": M}
        """
        actions = await self._fetch_actions_with_outcomes(agent_id)
        logger.info(
            f"ActionScorer.score_all: {len(actions)} actions with outcomes, "
            f"agent_id={agent_id}"
        )

        if not actions:
            return {"dimensions_updated": 0, "lessons_generated": 0}

        dimensions_updated = 0

        for dimension in DIMENSIONS:
            insights = self._aggregate_by_dimension(agent_id, actions, dimension)
            for insight in insights:
                await self._store.upsert_insight(
                    agent_id=agent_id,
                    dimension=dimension,
                    dimension_value=insight["dimension_value"],
                    sample_count=insight["sample_count"],
                    avg_views=insight["avg_views"],
                    avg_likes=insight["avg_likes"],
                    avg_comments=insight["avg_comments"],
                    author_reply_rate=insight.get("author_reply_rate"),
                )
                dimensions_updated += 1

        lessons = await self.generate_lessons(agent_id)

        logger.info(
            f"ActionScorer.score_all: done, dimensions_updated={dimensions_updated}, "
            f"lessons_generated={len(lessons)}"
        )
        return {
            "dimensions_updated": dimensions_updated,
            "lessons_generated": len(lessons),
        }

    def _aggregate_by_dimension(
        self,
        agent_id: str,
        actions: list[dict[str, Any]],
        dimension: str,
    ) -> list[dict[str, Any]]:
        """Group actions by dimension and compute averages.

        Args:
            agent_id: Agent identifier.
            actions: List of action+outcome dicts.
            dimension: One of DIMENSIONS.

        Returns:
            List of insight dicts with averages.
        """
        groups: dict[str, list[dict]] = defaultdict(list)

        for action in actions:
            key = self._extract_dimension_value(action, dimension)
            if key is None:
                continue
            groups[key].append(action)

        results = []
        for dim_value, group in groups.items():
            views = [a["views"] for a in group if a["views"] is not None]
            likes = [a["likes"] for a in group if a["likes"] is not None]
            comments = [a["comments"] for a in group if a["comments"] is not None]

            # Author reply rate only meaningful for comment actions
            replied_flags = [
                a["author_replied"]
                for a in group
                if a["author_replied"] is not None
            ]
            reply_rate = None
            if replied_flags:
                reply_rate = round(sum(1 for r in replied_flags if r) / len(replied_flags), 4)

            results.append({
                "dimension_value": str(dim_value),
                "sample_count": len(group),
                "avg_views": round(sum(views) / len(views), 2) if views else None,
                "avg_likes": round(sum(likes) / len(likes), 2) if likes else None,
                "avg_comments": round(sum(comments) / len(comments), 2) if comments else None,
                "author_reply_rate": reply_rate,
            })

        return results

    def _extract_dimension_value(
        self, action: dict[str, Any], dimension: str
    ) -> str | None:
        """Extract the grouping key for a given dimension."""
        if dimension == "author":
            return action.get("target_author")
        if dimension == "content_type":
            return action.get("content_type")
        if dimension == "topic":
            return action.get("topic")
        if dimension == "has_image":
            val = action.get("has_image")
            if val is None:
                return None
            return "true" if val else "false"
        if dimension == "hour":
            ts = action.get("timestamp_utc")
            if not ts:
                return None
            try:
                dt = datetime.fromisoformat(ts)
                return str(dt.hour)
            except (ValueError, TypeError):
                return None
        return None

    async def generate_lessons(self, agent_id: str) -> list[str]:
        """Generate automatic lessons from insights.

        Looks for patterns with sample_count >= 3 and produces
        human-readable lesson strings.

        Args:
            agent_id: Agent identifier.

        Returns:
            List of lesson strings.
        """
        insights = await self._store.get_insights(agent_id)
        if not insights:
            return []

        lessons: list[str] = []

        # Group insights by dimension for comparison
        by_dimension: dict[str, list[dict]] = defaultdict(list)
        for ins in insights:
            if ins["sample_count"] >= 3:
                by_dimension[ins["dimension"]].append(ins)

        lessons.extend(self._lessons_content_type(by_dimension.get("content_type", [])))
        lessons.extend(self._lessons_author(by_dimension.get("author", [])))
        lessons.extend(self._lessons_has_image(by_dimension.get("has_image", [])))
        lessons.extend(self._lessons_hour(by_dimension.get("hour", [])))

        logger.info(
            f"ActionScorer.generate_lessons: {len(lessons)} lessons, "
            f"agent_id={agent_id}"
        )
        return lessons

    def _confidence(self, sample_count: int) -> str:
        """Return confidence level based on sample size."""
        return "high" if sample_count >= 5 else "medium"

    def _lessons_content_type(self, insights: list[dict]) -> list[str]:
        """Generate lessons comparing content types."""
        lessons = []
        if len(insights) < 2:
            return lessons

        for i, a in enumerate(insights):
            for b in insights[i + 1:]:
                a_views = a.get("avg_views") or 0
                b_views = b.get("avg_views") or 0
                if b_views > 0 and a_views > 2 * b_views:
                    n = min(a["sample_count"], b["sample_count"])
                    conf = self._confidence(n)
                    lessons.append(
                        f"{a['dimension_value']} gets {a_views:.0f} avg views vs "
                        f"{b['dimension_value']} {b_views:.0f} — prefer "
                        f"{a['dimension_value']} [auto, n={n}, confidence: {conf}]"
                    )
                elif a_views > 0 and b_views > 2 * a_views:
                    n = min(a["sample_count"], b["sample_count"])
                    conf = self._confidence(n)
                    lessons.append(
                        f"{b['dimension_value']} gets {b_views:.0f} avg views vs "
                        f"{a['dimension_value']} {a_views:.0f} — prefer "
                        f"{b['dimension_value']} [auto, n={n}, confidence: {conf}]"
                    )
        return lessons

    def _lessons_author(self, insights: list[dict]) -> list[str]:
        """Generate lessons about target authors."""
        lessons = []
        for ins in insights:
            rate = ins.get("author_reply_rate")
            n = ins["sample_count"]
            conf = self._confidence(n)
            author = ins["dimension_value"]

            if rate is not None and rate > 0.3:
                lessons.append(
                    f"{author} replies {rate*100:.0f}% of the time — good target "
                    f"[auto, n={n}, confidence: {conf}]"
                )
            elif rate is not None and rate == 0.0:
                lessons.append(
                    f"{author} never replied ({n} attempts) — stop targeting "
                    f"[auto, n={n}, confidence: {conf}]"
                )
        return lessons

    def _lessons_has_image(self, insights: list[dict]) -> list[str]:
        """Generate lessons about image usage."""
        lessons = []
        by_val = {ins["dimension_value"]: ins for ins in insights}
        img_true = by_val.get("true")
        img_false = by_val.get("false")

        if not img_true or not img_false:
            return lessons

        true_views = img_true.get("avg_views") or 0
        false_views = img_false.get("avg_views") or 0

        if false_views > 0 and true_views > 2 * false_views:
            n = min(img_true["sample_count"], img_false["sample_count"])
            conf = self._confidence(n)
            lessons.append(
                f"Posts with images get {true_views:.0f} avg views vs "
                f"{false_views:.0f} without — always include images "
                f"[auto, n={n}, confidence: {conf}]"
            )
        elif true_views > 0 and false_views > 2 * true_views:
            n = min(img_true["sample_count"], img_false["sample_count"])
            conf = self._confidence(n)
            lessons.append(
                f"Posts without images get {false_views:.0f} avg views vs "
                f"{true_views:.0f} with — images may not help "
                f"[auto, n={n}, confidence: {conf}]"
            )
        return lessons

    def _lessons_hour(self, insights: list[dict]) -> list[str]:
        """Generate lessons about posting hours."""
        lessons = []
        if len(insights) < 2:
            return lessons

        # Find best and worst hours by avg_views
        with_views = [i for i in insights if i.get("avg_views") is not None]
        if len(with_views) < 2:
            return lessons

        best = max(with_views, key=lambda x: x["avg_views"])
        worst = min(with_views, key=lambda x: x["avg_views"])

        best_views = best["avg_views"] or 0
        worst_views = worst["avg_views"] or 0

        if worst_views > 0 and best_views > 2 * worst_views:
            n = min(best["sample_count"], worst["sample_count"])
            conf = self._confidence(n)
            lessons.append(
                f"Hour {best['dimension_value']}:00 UTC gets {best_views:.0f} avg views vs "
                f"hour {worst['dimension_value']}:00 UTC {worst_views:.0f} — "
                f"prefer posting around {best['dimension_value']}:00 UTC "
                f"[auto, n={n}, confidence: {conf}]"
            )
        return lessons

    async def _fetch_actions_with_outcomes(
        self, agent_id: str
    ) -> list[dict[str, Any]]:
        """Fetch all actions joined with collected outcomes from DB."""
        async with aiosqlite.connect(self._store.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(_ACTIONS_WITH_OUTCOMES_SQL, (agent_id,))
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
