"""Reflection bridge: spawn persona subagent to reflect on cycle results.

After execute, the persona reviews what happened and updates its living memory:
  - strategic_state.md — what I am building now
  - open_loops.md — unfinished threads, relationships to develop
  - intent.md — priorities for the next cycle
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger("bsq.operator.reflection_bridge")

_REFLECT_PROMPT_TEMPLATE = """You are {agent_id} reflecting on what just happened in your micro-cycle.

Read your briefing packet for full context:
- {agent_dir}/briefing_packet.md

Read your journal to see what actions were just taken:
- {agent_dir}/journal.md (check the most recent entries)

Now update three living documents based on what you learned this cycle:

1. **{agent_dir}/strategic_state.md** — What am I building right now?
   Update with any shifts in your positioning, new lines you are exploring,
   or hypotheses you confirmed/rejected. Keep it under 500 words.

2. **{agent_dir}/open_loops.md** — What threads are unfinished?
   Track: conversations to follow up on, authors to re-engage, topics to revisit,
   promises you made to yourself. Add new loops, close resolved ones.

3. **{agent_dir}/intent.md** — What do I want to do next cycle?
   Based on what just happened, what should the next cycle prioritize?
   Be specific: coins, post types, authors to engage, experiments to try.

Rules:
- Keep each file concise and actionable
- Remove stale entries (loops you resolved, intents that were fulfilled)
- Do not rewrite identity.md or style.md — those are stable
- Read each file first, then edit it — do not replace everything from scratch"""


async def reflect_on_cycle(
    agent_id: str,
    agent_dir: str,
    *,
    timeout_sec: int = 120,
) -> bool:
    """Spawn persona subagent to reflect and update living memory files.

    Returns True if reflection completed (even partial updates count).
    """
    prompt = _REFLECT_PROMPT_TEMPLATE.format(agent_id=agent_id, agent_dir=agent_dir)
    cmd = ["claude", "-p", prompt, "--allowedTools", "Read,Edit,Write"]

    logger.info("Spawning reflection subagent for %s (timeout=%ds)", agent_id, timeout_sec)

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
            logger.warning("Reflection subagent timed out for %s after %ds", agent_id, timeout_sec)
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()
            return False

        if proc.returncode != 0:
            stderr_text = (stderr or b"").decode(errors="replace")[:500]
            logger.warning("Reflection subagent failed for %s (rc=%d): %s", agent_id, proc.returncode, stderr_text)
            return False

        logger.info("Reflection completed for %s", agent_id)
        return True

    except FileNotFoundError:
        logger.error("claude CLI not found. Install Claude Code to use reflection_bridge.")
        return False
    except Exception as exc:
        logger.error("Reflection bridge error for %s: %s", agent_id, exc)
        return False
