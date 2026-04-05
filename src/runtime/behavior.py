"""HumanBehavior -- adds human-like patterns to browser actions.

Provides page warmup (scroll/pause before acting), variable delays between actions,
smooth mouse movement, and idle visits. Integrated into browser_actions before each action.
"""

import asyncio
import random
import logging

logger = logging.getLogger("bsq.runtime.behavior")


async def warm_up(page) -> None:
    """Simulate reading the page before acting: scroll, pause, scroll back."""
    total_down = 0
    steps = random.randint(2, 3)
    for _ in range(steps):
        delta = random.randint(200 // steps, 600 // steps)
        await page.mouse.wheel(0, delta)
        total_down += delta
        await asyncio.sleep(random.uniform(0.5, 1.5))

    await asyncio.sleep(random.uniform(3.0, 8.0))

    scroll_up = random.randint(50, 150)
    await page.mouse.wheel(0, -scroll_up)


async def mouse_move_to(page, selector: str) -> None:
    """Move mouse smoothly to element center with small random offset."""
    box = await page.locator(selector).first.bounding_box()
    if not box:
        return

    target_x = box["x"] + box["width"] / 2 + random.uniform(-5, 5)
    target_y = box["y"] + box["height"] / 2 + random.uniform(-5, 5)

    # Get current mouse position approximation (center of viewport as fallback)
    vp = page.viewport_size or {"width": 1280, "height": 720}
    current_x = vp["width"] / 2.0
    current_y = vp["height"] / 2.0

    num_steps = random.randint(3, 5)
    for i in range(1, num_steps + 1):
        ratio = i / num_steps
        x = current_x + (target_x - current_x) * ratio
        y = current_y + (target_y - current_y) * ratio
        await page.mouse.move(x, y)
        await asyncio.sleep(random.uniform(0.02, 0.05))


_DEFAULT_BUCKETS = [(0.60, 20, 35), (0.85, 35, 60), (0.95, 60, 90), (1.0, 5, 10)]


async def delay_between_actions(*, buckets: list[tuple[float, float, float]] | None = None) -> None:
    """Weighted random delay simulating variable human attention.

    buckets: list of (cumulative_probability, min_sec, max_sec).
    Falls back to _DEFAULT_BUCKETS when not provided (or loaded from policy).
    """
    chosen_buckets = buckets or _DEFAULT_BUCKETS
    roll = random.random()
    delay = random.uniform(chosen_buckets[-1][1], chosen_buckets[-1][2])
    for prob, lo, hi in chosen_buckets:
        if roll < prob:
            delay = random.uniform(lo, hi)
            break

    logger.debug(f"delay_between_actions: sleeping {delay:.1f}s")
    await asyncio.sleep(delay)


async def idle_visit(page, post_url: str) -> None:
    """Open a post page, scroll as if reading, then leave. No action taken."""
    try:
        await page.goto(post_url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(random.uniform(2.0, 4.0))

        # First scroll
        steps = random.randint(2, 3)
        for _ in range(steps):
            await page.mouse.wheel(0, random.randint(100, 200))
            await asyncio.sleep(random.uniform(0.4, 1.0))

        await asyncio.sleep(random.uniform(3.0, 8.0))

        # Second scroll
        for _ in range(random.randint(1, 2)):
            await page.mouse.wheel(0, random.randint(100, 200))
            await asyncio.sleep(random.uniform(0.3, 0.8))

        await asyncio.sleep(random.uniform(1.0, 3.0))
        logger.debug(f"idle_visit: visited {post_url}")
    except Exception as exc:
        logger.warning(f"idle_visit: failed for {post_url} -- {exc}")


def should_do_idle_visit(*, probability: float = 0.25) -> bool:
    """Return True with given probability to trigger an idle visit between actions."""
    return random.random() < probability
