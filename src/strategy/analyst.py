"""Strategy analyst — updates strategy.md based on performance data.

Runs by trigger (every N sessions or significant metric change), not every session.
Bootstrap: writes hardcoded exploration strategy.
Normal: prepare_context() returns structured text for the agent (Claude session)
to read and decide what to write to strategy.md.
"""

import logging
from pathlib import Path

from src.metrics.store import MetricsStore

logger = logging.getLogger("bsq.strategy.analyst")

BOOTSTRAP_THRESHOLD = 15


def _read_file(path: str) -> str:
    """Read a text file, return empty string if not found."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


class StrategyAnalyst:
    """Periodically updates strategy.md from performance insights."""

    def __init__(self, agent_dir: str, store: MetricsStore):
        self._agent_dir = agent_dir
        self._store = store

    async def should_run(self, agent_id: str) -> bool:
        """Check if analyst should run this session.

        Runs always during bootstrap (<15 sessions), then every 7 sessions.
        """
        total = await self._store.get_total_sessions(agent_id)
        if total < BOOTSTRAP_THRESHOLD:
            return True
        if total % 7 == 0:
            return True
        return False

    async def analyze(self, agent_id: str, market_summary: str) -> str | None:
        """Run strategy analysis.

        During bootstrap with insufficient data, writes a hardcoded
        exploration strategy and returns None.
        Otherwise returns prepare_context() result for the agent to act on.

        Args:
            agent_id: Agent identifier.
            market_summary: Brief market context string.

        Returns:
            Context string for the agent, or None if bootstrap strategy was written.
        """
        total = await self._store.get_total_sessions(agent_id)
        insights = await self._store.get_insights(agent_id)

        # Check if we have enough data: need sample_count >= 3
        # for content_type AND author dimensions specifically (per bootstrap spec)
        key_dimensions = {"content_type", "author"}
        key_insights = [i for i in insights if i["dimension"] in key_dimensions]
        min_samples = min(
            (i["sample_count"] for i in key_insights), default=0
        ) if key_insights else 0

        if total < BOOTSTRAP_THRESHOLD and min_samples < 3:
            self._write_bootstrap_strategy()
            logger.info(
                "StrategyAnalyst.analyze: bootstrap strategy written, "
                "total_sessions=%d, min_samples=%d, agent_id=%s",
                total, min_samples, agent_id,
            )
            return None

        context = self.prepare_context(agent_id, market_summary, total)
        logger.info(
            "StrategyAnalyst.analyze: context prepared for agent, "
            "agent_id=%s, total_sessions=%d",
            agent_id, total,
        )
        return context

    def prepare_context(
        self, agent_id: str, market_summary: str, total_sessions: int = 0
    ) -> str:
        """Prepare structured context for the agent to update strategy.

        Returns formatted text with performance data, relationships, lessons,
        and current strategy for the agent to analyze and rewrite strategy.md.

        Args:
            agent_id: Agent identifier.
            market_summary: Brief market context string.
            total_sessions: Total session count (pass from analyze or 0).

        Returns:
            Formatted markdown string with all context for strategy update.
        """
        performance = _read_file(str(Path(self._agent_dir) / "performance.md"))
        relationships = _read_file(str(Path(self._agent_dir) / "relationships.md"))
        lessons = _read_file(str(Path(self._agent_dir) / "lessons.md"))
        tactics = _read_file(str(Path(self._agent_dir) / "tactics.md"))
        current_strategy = _read_file(str(Path(self._agent_dir) / "strategy.md"))

        sections = [
            "# Strategy Analysis Context",
            "",
            f"## Agent: {agent_id}",
            f"Total sessions: {total_sessions}",
            "",
            "## Current Strategy",
            current_strategy if current_strategy else "(no strategy.md yet)",
            "",
            "## Performance Data",
            performance if performance else "(no performance data yet)",
            "",
            "## Relationships",
            relationships if relationships else "(no relationships yet)",
            "",
            "## Lessons Learned",
            lessons if lessons else "(no lessons yet)",
            "",
            "## Tactics",
            tactics if tactics else "(no tactics yet)",
            "",
            "## Market Context",
            market_summary if market_summary else "(no market summary)",
            "",
            "## What to Update in strategy.md",
            "- Current phase and status",
            "- Content mix percentages (must sum to 100%)",
            "- Key relationships to nurture/avoid",
            "- Engagement rules",
            "- Next session priorities",
        ]

        context = "\n".join(sections)
        logger.info(
            "StrategyAnalyst.prepare_context: prepared, agent_id=%s, "
            "has_performance=%s, has_relationships=%s, has_lessons=%s",
            agent_id,
            bool(performance),
            bool(relationships),
            bool(lessons),
        )
        return context

    def _write_bootstrap_strategy(self) -> None:
        """Write a hardcoded exploration strategy for bootstrap phase."""
        content = (
            "# Current Strategy\n\n"
            "## Current Phase: Bootstrap (Exploration)\n\n"
            "## Focus\n"
            "- 60% comments on varied authors (test different follower ranges)\n"
            "- 25% posts with images (rotate types: analysis, meme, hot take, news)\n"
            "- 15% reply-to-replies + follows\n\n"
            "## Rules\n"
            "- Never two posts of same type in a row\n"
            "- Never three comments on same author in one session\n"
            "- Vary session times (morning, afternoon, evening)\n"
            "- Minimum per session: 3 posts + 20 comments + 20 likes\n\n"
            "## Content Mix\n"
            "- Market analysis with chart: 40%\n"
            "- Hot takes on news: 30%\n"
            "- Relatable mood posts: 20%\n"
            "- Quote reposts: 10%\n\n"
            "## Engagement Targets\n"
            "- Comment on posts with 10-100 likes (sweet spot)\n"
            "- Like every post you comment on\n"
            "- Follow authors who reply to your comments\n"
            "- Reply to all replies on your posts\n"
        )
        strategy_path = Path(self._agent_dir) / "strategy.md"
        strategy_path.write_text(content, encoding="utf-8")
        logger.info(
            "StrategyAnalyst._write_bootstrap_strategy: written to %s",
            strategy_path,
        )
