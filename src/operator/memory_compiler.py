"""Memory compiler: builds a compact briefing packet for persona subagent.

Reads all memory layers (identity, strategy, episodes, lessons, relationships)
and compiles a single briefing_packet.md that the persona receives as context.

The persona gets this instead of reading 12 separate files.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("bsq.operator.memory_compiler")

# Max characters per section to keep briefing compact
_IDENTITY_LIMIT = 2000
_STRATEGIC_STATE_LIMIT = 1500
_OPEN_LOOPS_LIMIT = 1000
_INTENT_LIMIT = 800
_LESSONS_TAIL = 1500
_JOURNAL_TAIL = 2000
_RELATIONSHIPS_TAIL = 1200
_PERFORMANCE_TAIL = 800


_PLACEHOLDER_MARKERS = ("(none yet", "(agent fills", "(placeholder", "(unfilled", "(empty")


def _is_placeholder(text: str) -> bool:
    """Check if text contains only placeholder/template content."""
    lowered = text.lower()
    # Strip headings and blank lines, check if anything substantive remains
    lines = [line.strip() for line in lowered.split("\n") if line.strip() and not line.strip().startswith("#")]
    if not lines:
        return True
    return all(any(marker in line for marker in _PLACEHOLDER_MARKERS) for line in lines)


def compile_briefing_packet(agent_dir: str, agent_id: str) -> str:
    """Compile all memory layers into a single briefing packet.

    Returns the compiled text. Also writes to agents/{id}/briefing_packet.md.
    """
    agent_path = Path(agent_dir)
    sections: list[str] = []

    # 1. WHO I AM (stable identity)
    sections.append("# WHO I AM")
    sections.append(_read_trimmed(agent_path / "identity.md", _IDENTITY_LIMIT))
    sections.append("")
    style = _read_trimmed(agent_path / "style.md", 800)
    if style:
        sections.append("## Writing style")
        sections.append(style)
        sections.append("")

    # 2. WHAT I AM BUILDING (strategic state — living document)
    sections.append("# WHAT I AM BUILDING")
    strategic = _read_trimmed(agent_path / "strategic_state.md", _STRATEGIC_STATE_LIMIT)
    if strategic:
        sections.append(strategic)
    else:
        # Fallback to static strategy.md
        sections.append(_read_trimmed(agent_path / "strategy.md", _STRATEGIC_STATE_LIMIT))
    sections.append("")

    # 3. OPEN LOOPS (unfinished threads, relationships to develop)
    open_loops = _read_trimmed(agent_path / "open_loops.md", _OPEN_LOOPS_LIMIT)
    if open_loops and not _is_placeholder(open_loops):
        sections.append("# OPEN LOOPS")
        sections.append(open_loops)
        sections.append("")

    # 4. MY INTENT (what I want to do this cycle)
    intent = _read_trimmed(agent_path / "intent.md", _INTENT_LIMIT)
    if intent and not _is_placeholder(intent):
        sections.append("# MY INTENT FOR THIS CYCLE")
        sections.append(intent)
        sections.append("")

    # 5. RECENT LESSONS (semantic memory — what works, what doesn't)
    lessons = _read_tail(agent_path / "lessons.md", _LESSONS_TAIL)
    if lessons:
        sections.append("# RECENT LESSONS")
        sections.append(lessons)
        sections.append("")

    # 6. RECENT JOURNAL (episodic memory — what happened)
    journal = _read_tail(agent_path / "journal.md", _JOURNAL_TAIL)
    if journal:
        sections.append("# RECENT ACTIVITY")
        sections.append(journal)
        sections.append("")

    # 7. RELATIONSHIP PRIORITIES (social memory)
    relationships = _read_tail(agent_path / "relationships.md", _RELATIONSHIPS_TAIL)
    if relationships:
        sections.append("# RELATIONSHIP PRIORITIES")
        sections.append(relationships)
        sections.append("")

    # 8. PERFORMANCE SIGNALS (what's working)
    performance = _read_tail(agent_path / "performance.md", _PERFORMANCE_TAIL)
    if performance:
        sections.append("# PERFORMANCE SIGNALS")
        sections.append(performance)
        sections.append("")

    # 9. SUPERVISOR FEEDBACK (external coaching)
    feedback = _read_tail(agent_path / "supervisor_feedback.md", 600)
    if feedback:
        sections.append("# SUPERVISOR FEEDBACK")
        sections.append(feedback)
        sections.append("")

    # 10. HARD CONSTRAINTS
    sections.append("# HARD CONSTRAINTS")
    sections.append("- Every coin mention must use $CASHTAG")
    sections.append("- Do not end any paragraph with a trailing period")
    sections.append("- Public text comes from you, not from code")
    sections.append("- Do not copy the other agent's style or territory")
    sections.append("")

    packet = "\n".join(sections)

    # Write to file for reference
    packet_path = agent_path / "briefing_packet.md"
    try:
        packet_path.write_text(packet, encoding="utf-8")
        logger.info("Compiled briefing packet for %s (%d chars)", agent_id, len(packet))
    except Exception as exc:
        logger.warning("Failed to write briefing packet for %s: %s", agent_id, exc)

    return packet


def _read_trimmed(path: Path, limit: int) -> str:
    """Read file and trim to limit characters."""
    if not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        return text[:limit] if len(text) > limit else text
    except Exception:
        return ""


def _read_tail(path: Path, limit: int) -> str:
    """Read the last `limit` characters of a file (most recent content).

    Snaps to the first newline after slicing to avoid truncated lines.
    """
    if not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        if len(text) <= limit:
            return text
        tail = text[-limit:]
        nl = tail.find("\n")
        if nl != -1 and nl < 200:
            tail = tail[nl + 1:]
        return tail
    except Exception:
        return ""
