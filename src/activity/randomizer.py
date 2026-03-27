"""Human-like randomization for activity engine."""

import random
import asyncio
import logging

logger = logging.getLogger("bsq.activity")


class HumanRandomizer:
    """Simulate human-like delays and random skipping."""

    def __init__(self, delay_range: tuple[int, int] = (30, 120), skip_rate: float = 0.35):
        self._delay_range = delay_range
        self._skip_rate = skip_rate

    def should_skip(self) -> bool:
        """Randomly decide whether to skip an action."""
        return random.random() < self._skip_rate

    async def human_delay(self) -> float:
        """Wait a random human-like delay. Returns actual delay in seconds."""
        delay = random.uniform(*self._delay_range)
        logger.debug(f"Human delay: {delay:.1f}s")
        await asyncio.sleep(delay)
        return delay
