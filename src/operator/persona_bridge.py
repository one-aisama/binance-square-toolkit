"""Persona bridge: spawn persona subagent to write text into pending plan.

The bridge does NOT generate text. It spawns a Claude Code CLI subagent
which reads the plan, writes text for each action, and saves back.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from src.runtime.plan_io import plan_has_text

logger = logging.getLogger("bsq.operator.persona_bridge")

# Prompt template for persona subagent
_AUTHOR_PROMPT_TEMPLATE = """You are {agent_id}.

Read your briefing packet first — it contains everything you need to know about who you are,
what you are building, your recent activity, and your current intent:
- agents/{agent_id}/briefing_packet.md

Check if a strategic directive exists for this cycle:
- data/runtime/{agent_id}/strategic_directive.json
If it exists, read it — it contains your strategic decisions for this cycle: focus, tone,
coin preferences, and post direction. Let it guide your writing voice and angle selection.

Task: Read the plan file at {plan_path} and write text for every action that has "text": null.

For each COMMENT action:
- Read "target_text" (the post you're replying to)
- Write a short, relevant reply (1-2 sentences)
- Sound like your public voice, not an assistant
- Add your own angle or pushback
- Save it in the "text" field

For each POST action:
- Read "brief_context" (topic, angle, coin, market data)
- Write 2-3 paragraphs
- Every coin mention must use $CASHTAG
- Do not end paragraphs with a period
- Make it consistent with your strategic state, intent, and directive tone
- Save it in the "text" field

After writing all texts, save the updated plan back to {plan_path}.
Do not change any other fields. Only fill in "text" where it is null."""


async def author_plan_text(
    agent_id: str,
    agent_dir: str,
    plan_path: str,
    *,
    timeout_sec: int = 600,
    mode: str = "cli",
) -> bool:
    """Spawn persona subagent to write text into pending plan.

    Returns True if text was authored successfully, False on timeout/error.
    """
    if plan_has_text(agent_id):
        logger.info("Plan already has text for %s, skipping authoring", agent_id)
        return True

    if mode == "cli":
        return await _author_via_cli(agent_id, agent_dir, plan_path, timeout_sec=timeout_sec)

    logger.error("Unknown persona_bridge mode: %s", mode)
    return False


async def _author_via_cli(
    agent_id: str,
    agent_dir: str,
    plan_path: str,
    *,
    timeout_sec: int = 600,
) -> bool:
    """Spawn claude CLI as subprocess to author text.

    Uses asyncio.create_subprocess_exec (not shell) to avoid injection.
    """
    prompt = _AUTHOR_PROMPT_TEMPLATE.format(
        agent_id=agent_id,
        plan_path=plan_path,
    )

    cmd = ["claude", "-p", prompt, "--allowedTools", "Edit,Read,Write"]

    logger.info("Spawning persona subagent for %s (timeout=%ds)", agent_id, timeout_sec)

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
            logger.warning("Persona subagent timed out for %s after %ds", agent_id, timeout_sec)
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()
            return False

        if proc.returncode != 0:
            stderr_text = (stderr or b"").decode(errors="replace")[:500]
            logger.warning("Persona subagent failed for %s (rc=%d): %s", agent_id, proc.returncode, stderr_text)
            return False

        if plan_has_text(agent_id):
            logger.info("Persona subagent authored text for %s", agent_id)
            return True

        logger.warning("Persona subagent completed but plan still has no text for %s", agent_id)
        return False

    except FileNotFoundError:
        logger.error("claude CLI not found. Install Claude Code to use persona_bridge CLI mode.")
        return False
    except Exception as exc:
        logger.error("Persona bridge error for %s: %s", agent_id, exc)
        return False
