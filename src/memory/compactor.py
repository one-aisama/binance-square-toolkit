"""Memory compactor — generates performance.md, relationships.md from insights.

Deterministic (no LLM): reads SQLite insights, writes markdown files.
Also handles journal archiving and lessons TTL cleanup.
"""

import os
import re
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src.metrics.store import MetricsStore

logger = logging.getLogger("bsq.memory.compactor")

LESSONS_TTL_DAYS = 30
MAX_JOURNAL_SESSIONS = 5


async def generate_performance(
    store: MetricsStore, agent_id: str, agent_dir: str
) -> bool:
    """Generate performance.md from insights table. Pure code, no LLM."""
    insights = await store.get_insights(agent_id)
    if not insights:
        logger.info(f"No insights for {agent_id}, skipping performance.md")
        return False

    lines = ["# Performance Report", "", f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", ""]

    # Content type performance
    content_insights = [i for i in insights if i["dimension"] == "content_type"]
    if content_insights:
        lines.append("## Content Types")
        lines.append("")
        lines.append("| Type | Posts | Avg Views | Avg Likes | Avg Comments |")
        lines.append("|------|-------|-----------|-----------|-------------|")
        for row in sorted(content_insights, key=lambda x: x["sample_count"], reverse=True):
            lines.append(
                f"| {row['dimension_value']} | {row['sample_count']} | "
                f"{_fmt(row['avg_views'])} | {_fmt(row['avg_likes'])} | "
                f"{_fmt(row['avg_comments'])} |"
            )
        lines.append("")

    # Author engagement
    author_insights = [i for i in insights if i["dimension"] == "author"]
    if author_insights:
        lines.append("## Comment Targets (by author)")
        lines.append("")
        lines.append("| Author | Comments | Avg Likes | Reply Rate |")
        lines.append("|--------|----------|-----------|------------|")
        for row in sorted(author_insights, key=lambda x: x["sample_count"], reverse=True):
            reply_rate = f"{row['author_reply_rate']:.0%}" if row["author_reply_rate"] is not None else "n/a"
            lines.append(
                f"| {row['dimension_value']} | {row['sample_count']} | "
                f"{_fmt(row['avg_likes'])} | {reply_rate} |"
            )
        lines.append("")

    # Time of day
    hour_insights = [i for i in insights if i["dimension"] == "hour"]
    if hour_insights:
        lines.append("## Best Times (UTC)")
        lines.append("")
        sorted_hours = sorted(hour_insights, key=lambda x: x["avg_likes"] or 0, reverse=True)
        for row in sorted_hours[:5]:
            lines.append(
                f"- {row['dimension_value']}:00 UTC — "
                f"avg likes: {_fmt(row['avg_likes'])}, "
                f"sample: {row['sample_count']}"
            )
        lines.append("")

    # Image impact
    image_insights = [i for i in insights if i["dimension"] == "has_image"]
    if image_insights:
        lines.append("## Image Impact")
        lines.append("")
        for row in image_insights:
            label = "With image" if row["dimension_value"].lower() == "true" else "Without image"
            lines.append(
                f"- {label}: avg views {_fmt(row['avg_views'])}, "
                f"avg likes {_fmt(row['avg_likes'])}, "
                f"sample: {row['sample_count']}"
            )
        lines.append("")

    path = Path(agent_dir) / "performance.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"Generated {path}")
    return True


async def generate_relationships(
    store: MetricsStore, agent_id: str, agent_dir: str
) -> bool:
    """Generate relationships.md from author insights. Pure code, no LLM."""
    author_insights = await store.get_insights(agent_id, dimension="author")
    if not author_insights:
        logger.info(f"No author insights for {agent_id}, skipping relationships.md")
        return False

    lines = ["# Relationships", "", f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", ""]

    for row in sorted(author_insights, key=lambda x: x["sample_count"], reverse=True):
        reply_rate = row["author_reply_rate"]
        reply_pct = f"{reply_rate:.0%}" if reply_rate is not None else "unknown"
        verdict = _relationship_verdict(row)

        lines.append(f"## {row['dimension_value']}")
        lines.append(f"- interactions: {row['sample_count']}")
        lines.append(f"- author_reply_rate: {reply_pct}")
        lines.append(f"- avg_likes: {_fmt(row['avg_likes'])}")
        lines.append(f"- verdict: {verdict}")
        lines.append("")

    path = Path(agent_dir) / "relationships.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"Generated {path}")
    return True


def archive_journal(agent_dir: str) -> None:
    """Move old sessions from journal.md to archive/. Keep last N sessions."""
    journal_path = Path(agent_dir) / "journal.md"
    if not journal_path.exists():
        return

    content = journal_path.read_text(encoding="utf-8")
    sessions = re.split(r"(?=^## Session \d+)", content, flags=re.MULTILINE)

    header = sessions[0] if sessions and not sessions[0].startswith("## Session") else ""
    session_blocks = [s for s in sessions if s.startswith("## Session")]

    if len(session_blocks) <= MAX_JOURNAL_SESSIONS:
        return

    to_archive = session_blocks[:-MAX_JOURNAL_SESSIONS]
    to_keep = session_blocks[-MAX_JOURNAL_SESSIONS:]

    # Write archive
    archive_dir = Path(agent_dir) / "archive"
    archive_dir.mkdir(exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    archive_path = archive_dir / f"journal_{timestamp}.md"
    archive_path.write_text("\n".join(to_archive), encoding="utf-8")

    # Rewrite journal with only recent sessions
    journal_path.write_text(header.rstrip("\n") + "\n\n" + "\n".join(to_keep), encoding="utf-8")
    logger.info(f"Archived {len(to_archive)} sessions, kept {len(to_keep)}")


def cleanup_lessons(agent_dir: str) -> int:
    """Remove manual lessons older than TTL_DAYS. Returns count removed."""
    lessons_path = Path(agent_dir) / "lessons.md"
    if not lessons_path.exists():
        return 0

    content = lessons_path.read_text(encoding="utf-8")
    lines = content.split("\n")
    cutoff = datetime.utcnow() - timedelta(days=LESSONS_TTL_DAYS)
    kept = []
    removed = 0

    for line in lines:
        if "[manual" in line:
            # Try to extract date from lesson line
            date_match = re.search(r"(\d{4}-\d{2}-\d{2})", line)
            if date_match:
                try:
                    lesson_date = datetime.strptime(date_match.group(1), "%Y-%m-%d")
                    if lesson_date < cutoff:
                        removed += 1
                        continue
                except ValueError:
                    pass
        kept.append(line)

    if removed > 0:
        lessons_path.write_text("\n".join(kept), encoding="utf-8")
        logger.info(f"Removed {removed} stale manual lessons from {lessons_path}")

    return removed


async def run_compaction(
    store: MetricsStore, agent_id: str, agent_dir: str
) -> dict:
    """Run full compaction cycle. Called by pipeline.py."""
    result = {
        "performance_generated": False,
        "relationships_generated": False,
        "sessions_archived": 0,
        "lessons_cleaned": 0,
    }

    result["performance_generated"] = await generate_performance(store, agent_id, agent_dir)
    result["relationships_generated"] = await generate_relationships(store, agent_id, agent_dir)

    archive_journal(agent_dir)
    result["lessons_cleaned"] = cleanup_lessons(agent_dir)

    return result


def _fmt(val: float | None) -> str:
    """Format a float for display, or 'n/a' if None."""
    if val is None:
        return "n/a"
    if val >= 100:
        return f"{val:.0f}"
    return f"{val:.1f}"


def _relationship_verdict(row: dict) -> str:
    """Generate a simple verdict for an author relationship."""
    reply_rate = row.get("author_reply_rate")
    sample = row.get("sample_count", 0)

    if sample < 3:
        return "NEEDS MORE DATA"
    if reply_rate is not None and reply_rate == 0:
        return "NOT WORTH TARGETING — never replies"
    if reply_rate is not None and reply_rate >= 0.3:
        return "HIGH VALUE — engages consistently"
    if reply_rate is not None and reply_rate > 0:
        return "MODERATE — occasional engagement"
    return "UNKNOWN"
