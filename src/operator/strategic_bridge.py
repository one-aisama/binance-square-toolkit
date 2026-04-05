"""Strategic bridge: spawn persona subagent to produce a strategic directive.

The persona reads their briefing packet + latest context summary and outputs
a strategic directive that tells the planner WHAT to focus on this cycle.

Writes:
  data/runtime/{agent_id}/strategic_directive.json
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("bsq.operator.strategic_bridge")

_STRATEGIZE_PROMPT_TEMPLATE = """You are {agent_id} making strategic decisions for your next micro-cycle.

Read your briefing packet — it contains who you are, what you are building, your open loops,
and your recent activity:
- {agent_dir}/briefing_packet.md

{context_section}

Based on your identity, current strategic state, and market context, decide what to focus on.
Write your directive as a JSON file at {directive_path}.

The JSON must have these fields:
- "focus_summary": string — one sentence: what are you focusing on and why
- "preferred_coins": list[str] — coins you want to post about (uppercase, e.g. ["SOL", "ETH"])
- "avoid_coins": list[str] — coins to skip this cycle (uppercase)
- "post_direction": string — what kind of post to write (e.g. "market_chart on SOL breakout")
- "comment_direction": string — what threads to engage with (e.g. "macro threads, skip meme")
- "skip_families": list[str] — post families to avoid (e.g. ["editorial_note"])
- "tone": string — tone guidance for this cycle (e.g. "analytical, cautious")

Keep it short and decisive. This is a planning step, not content creation.
Write ONLY the JSON file, nothing else."""


def _find_latest_context_summary(agent_id: str) -> str | None:
    """Find the most recent context markdown for this agent."""
    context_dir = Path("data/session_context")
    if not context_dir.exists():
        return None
    candidates = sorted(context_dir.glob(f"*_{agent_id}.md"), reverse=True)
    if not candidates:
        return None
    return str(candidates[0])


def _load_directive(agent_id: str) -> dict[str, Any] | None:
    """Load strategic directive from disk. Returns None if missing or invalid."""
    path = Path(f"data/runtime/{agent_id}/strategic_directive.json")
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "focus_summary" in data:
            return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load directive for %s: %s", agent_id, exc)
    return None


def load_strategic_directive(agent_id: str) -> dict[str, Any] | None:
    """Public API: load existing directive for planner to consume."""
    return _load_directive(agent_id)


async def generate_strategic_directive(
    agent_id: str,
    agent_dir: str,
    *,
    timeout_sec: int = 120,
) -> bool:
    """Spawn persona subagent to write a strategic directive.

    Returns True if directive was written successfully.
    """
    directive_path = f"data/runtime/{agent_id}/strategic_directive.json"
    Path(directive_path).parent.mkdir(parents=True, exist_ok=True)

    context_file = _find_latest_context_summary(agent_id)
    if context_file:
        context_section = f"Read the latest market context summary:\n- {context_file}"
    else:
        context_section = (
            "No previous context summary available. "
            "Base your decisions on your briefing packet alone."
        )

    prompt = _STRATEGIZE_PROMPT_TEMPLATE.format(
        agent_id=agent_id,
        agent_dir=agent_dir,
        context_section=context_section,
        directive_path=directive_path,
    )

    cmd = ["claude", "-p", prompt, "--allowedTools", "Read,Write"]

    logger.info("Spawning strategic subagent for %s (timeout=%ds)", agent_id, timeout_sec)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(Path.cwd()),
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout_sec,
            )
        except asyncio.TimeoutError:
            logger.warning("Strategic subagent timed out for %s after %ds", agent_id, timeout_sec)
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()
            return False

        if proc.returncode != 0:
            stderr_text = (stderr or b"").decode(errors="replace")[:500]
            logger.warning("Strategic subagent failed for %s (rc=%d): %s", agent_id, proc.returncode, stderr_text)
            return False

        directive = _load_directive(agent_id)
        if directive:
            logger.info(
                "Strategic directive for %s: %s (coins=%s)",
                agent_id,
                directive.get("focus_summary", "")[:80],
                directive.get("preferred_coins", []),
            )
            return True

        logger.warning("Strategic subagent completed but no valid directive for %s", agent_id)
        return False

    except FileNotFoundError:
        logger.error("claude CLI not found. Install Claude Code to use strategic_bridge.")
        return False
    except Exception as exc:
        logger.error("Strategic bridge error for %s: %s", agent_id, exc)
        return False
