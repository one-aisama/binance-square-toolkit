"""Session reviewer — records session stats and prepares review context.

Two parts:
1. Code: records session_stats to MetricsStore + appends journal (deterministic, always runs)
2. Context: prepare_review_context() returns formatted text for the agent
   (Claude session) to read and decide what lessons to add.
"""

import logging
from datetime import datetime
from pathlib import Path

from src.metrics.store import MetricsStore

logger = logging.getLogger("bsq.strategy.reviewer")


class SessionReviewer:
    """Records session stats and prepares review context for the agent."""

    def __init__(self, store: MetricsStore, agent_dir: str):
        self._store = store
        self._agent_dir = agent_dir

    async def review(
        self,
        session_id: str,
        agent_id: str,
        started_at: str,
        plan: list[dict],
        results: list[dict],
        guard_stats: dict,
    ) -> str:
        """Review a completed session: save stats, append journal, prepare context.

        Args:
            session_id: Unique session identifier.
            agent_id: Agent identifier.
            started_at: ISO timestamp when session started.
            plan: Original action plan (list of action dicts).
            results: Execution results (list of dicts with action + success + error).
            guard_stats: Guard/circuit breaker stats dict.

        Returns:
            Formatted review context string for the agent to generate lessons.
        """
        ended_at = datetime.utcnow().isoformat()

        planned_actions = len(plan)
        executed_actions = len(results)
        successful = sum(1 for r in results if r.get("success", False))
        failed = executed_actions - successful

        circuits_opened = guard_stats.get("circuits_opened", [])
        if not isinstance(circuits_opened, list):
            circuits_opened = []

        # Calculate duration in minutes for efficiency
        duration_minutes = 1.0
        try:
            start_dt = datetime.fromisoformat(started_at)
            end_dt = datetime.fromisoformat(ended_at)
            duration_minutes = max((end_dt - start_dt).total_seconds() / 60.0, 1.0)
        except (ValueError, TypeError):
            pass

        efficiency = round(successful / duration_minutes, 4)

        # Code part: always save session stats
        await self._store.save_session_stats(
            session_id=session_id,
            agent_id=agent_id,
            started_at=started_at,
            ended_at=ended_at,
            planned_actions=planned_actions,
            executed_actions=executed_actions,
            successful_actions=successful,
            failed_actions=failed,
            circuits_opened=circuits_opened,
            efficiency=efficiency,
        )
        logger.info(
            "SessionReviewer.review: stats saved, session_id=%s, "
            "planned=%d, executed=%d, successful=%d, failed=%d, efficiency=%.2f",
            session_id, planned_actions, executed_actions, successful, failed, efficiency,
        )

        # Build session summary for journal
        summary = (
            f"Planned: {planned_actions}, Executed: {executed_actions}, "
            f"Successful: {successful}, Failed: {failed}\n"
            f"Duration: {duration_minutes:.1f}min, Efficiency: {efficiency:.2f} actions/min"
        )
        if circuits_opened:
            summary += f"\nCircuits opened: {', '.join(circuits_opened)}"

        # Action breakdown
        action_types = {}
        for r in results:
            atype = r.get("action", "unknown")
            action_types[atype] = action_types.get(atype, 0) + 1
        if action_types:
            breakdown = ", ".join(f"{k}={v}" for k, v in sorted(action_types.items()))
            summary += f"\nActions: {breakdown}"

        self._append_to_journal(session_id, summary)

        # Prepare review context for the agent
        context = self.prepare_review_context(plan, results, guard_stats)
        return context

    def prepare_review_context(
        self,
        plan: list[dict],
        results: list[dict],
        guard_stats: dict,
    ) -> str:
        """Prepare session summary for the agent to generate lessons.

        Returns formatted text. The agent reads it and decides what to
        add to lessons.md and journal.md.

        Args:
            plan: Original action plan.
            results: Execution results with action, success, error fields.
            guard_stats: Guard/circuit breaker stats.

        Returns:
            Formatted markdown string with session review data.
        """
        planned = len(plan)
        executed = len(results)
        successful = sum(1 for r in results if r.get("success", False))
        failed = executed - successful

        circuits_opened = guard_stats.get("circuits_opened", [])
        if not isinstance(circuits_opened, list):
            circuits_opened = []

        # Action breakdown
        action_types: dict[str, dict[str, int]] = {}
        for r in results:
            atype = r.get("action", "unknown")
            if atype not in action_types:
                action_types[atype] = {"success": 0, "fail": 0}
            if r.get("success", False):
                action_types[atype]["success"] += 1
            else:
                action_types[atype]["fail"] += 1

        breakdown_lines = []
        for atype, counts in sorted(action_types.items()):
            breakdown_lines.append(
                f"- {atype}: {counts['success']} ok, {counts['fail']} failed"
            )
        breakdown_str = "\n".join(breakdown_lines) if breakdown_lines else "(no actions)"

        # Failed actions detail
        failed_lines = []
        for r in results:
            if not r.get("success", False):
                error = r.get("error", "unknown error")
                action = r.get("action", "unknown")
                target = r.get("target", "")
                failed_lines.append(f"- {action} (target={target}): {error}")
        failed_str = "\n".join(failed_lines) if failed_lines else "(none)"

        # Skipped actions (planned but not executed)
        executed_targets = {r.get("target") for r in results}
        skipped = [
            a for a in plan
            if a.get("target") not in executed_targets
            and a.get("action") in {"comment", "like", "follow", "quote_repost"}
        ]
        skipped_lines = []
        for s in skipped:
            skipped_lines.append(f"- {s.get('action')} target={s.get('target')}: {s.get('reason', '')}")
        skipped_str = "\n".join(skipped_lines) if skipped_lines else "(none)"

        # Current lessons for deduplication
        current_lessons = self._read_lessons()

        sections = [
            "# Session Review Context",
            "",
            "## Summary",
            f"Planned: {planned}, Executed: {executed}, Successful: {successful}, Failed: {failed}",
            "",
            "## Action Breakdown",
            breakdown_str,
            "",
            "## Failed Actions",
            failed_str,
            "",
            "## Skipped Actions (planned but not executed)",
            skipped_str,
            "",
            "## Guard Stats",
            f"Circuits opened: {', '.join(circuits_opened) if circuits_opened else 'none'}",
            "",
            "## Current Lessons (for deduplication)",
            current_lessons if current_lessons else "(no lessons yet)",
            "",
            "## What to Do",
            "- Add 0-2 new lessons to lessons.md (only genuinely new observations)",
            "- Each lesson: one line, actionable, with [manual, YYYY-MM-DD] tag",
            "- Do NOT duplicate existing lessons",
        ]

        context = "\n".join(sections)
        logger.info(
            "SessionReviewer.prepare_review_context: prepared, "
            "planned=%d, executed=%d, successful=%d",
            planned, executed, successful,
        )
        return context

    def _append_to_journal(self, session_id: str, summary: str) -> None:
        """Append session summary to journal.md."""
        journal_path = Path(self._agent_dir) / "journal.md"
        today = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

        block = f"\n## Session {session_id} — {today}\n{summary}\n"

        existing = ""
        if journal_path.exists():
            existing = journal_path.read_text(encoding="utf-8")

        journal_path.write_text(existing + block, encoding="utf-8")
        logger.info(
            "SessionReviewer._append_to_journal: appended session %s", session_id
        )

    def _append_lessons(self, lessons: list[str]) -> None:
        """Append new lessons to lessons.md with [manual, date] tag."""
        if not lessons:
            return

        lessons_path = Path(self._agent_dir) / "lessons.md"
        today = datetime.utcnow().strftime("%Y-%m-%d")

        existing = ""
        if lessons_path.exists():
            existing = lessons_path.read_text(encoding="utf-8")

        new_lines = []
        for lesson in lessons:
            line = f"- {lesson.strip()} [manual, {today}]"
            new_lines.append(line)

        updated = existing.rstrip() + "\n" + "\n".join(new_lines) + "\n"
        lessons_path.write_text(updated, encoding="utf-8")
        logger.info(
            "SessionReviewer._append_lessons: added %d lessons", len(lessons)
        )

    def _read_lessons(self) -> str:
        """Read current lessons.md content."""
        lessons_path = Path(self._agent_dir) / "lessons.md"
        try:
            return lessons_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""
