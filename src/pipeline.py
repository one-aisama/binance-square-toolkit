"""Metrics pipeline — runs collector -> scorer -> compactor -> [analyst].

Single script, single cron job. Runs before agent sessions.
If pipeline fails, session starts with stale data (not broken).
"""

import asyncio
import logging
import sys
import time
from typing import Any

from src.metrics.store import MetricsStore, init_metrics_tables
from src.metrics.collector import MetricsCollector
from src.metrics.scorer import ActionScorer
from src.memory.compactor import run_compaction
from src.strategy.analyst import StrategyAnalyst

logger = logging.getLogger("bsq.pipeline")


async def run_pipeline(
    agent_id: str,
    agent_dir: str,
    db_path: str,
    sdk: Any = None,
) -> dict[str, Any]:
    """Run full metrics pipeline for an agent.

    Steps:
    1. Initialize metrics tables
    2. If sdk provided: collect delayed outcomes + profile snapshot
    3. Score all actions into insights
    4. Run memory compaction (performance.md, relationships.md, journal archive)
    5. If StrategyAnalyst.should_run: update strategy.md

    Each step is wrapped in try/except — one failure does not crash the pipeline.

    Args:
        agent_id: Agent identifier.
        agent_dir: Path to agent's directory (e.g., "agents/example_macro").
        db_path: Path to SQLite database.
        sdk: Optional BinanceSquareSDK instance (needed for collector).

    Returns:
        Summary dict with results from each step.
    """
    start_time = time.monotonic()
    summary: dict[str, Any] = {
        "collector": None,
        "scorer": None,
        "compactor": None,
        "analyst_ran": False,
        "errors": [],
    }

    # Step 0: ensure tables exist
    try:
        await init_metrics_tables(db_path)
    except Exception as exc:
        logger.error("run_pipeline: init_metrics_tables failed, error=%s", exc)
        summary["errors"].append(f"init_tables: {exc}")
        return summary

    store = MetricsStore(db_path)

    # Step 1: collect delayed outcomes
    if sdk is not None:
        try:
            collector = MetricsCollector(store, sdk)
            summary["collector"] = await collector.collect_all(agent_id)
            await collector.collect_profile_snapshot(agent_id)
        except Exception as exc:
            logger.error("run_pipeline: collector failed, error=%s", exc)
            summary["errors"].append(f"collector: {exc}")

    # Step 2: score actions into insights
    try:
        scorer = ActionScorer(store)
        summary["scorer"] = await scorer.score_all(agent_id)
    except Exception as exc:
        logger.error("run_pipeline: scorer failed, error=%s", exc)
        summary["errors"].append(f"scorer: {exc}")

    # Step 3: compact memory files
    try:
        summary["compactor"] = await run_compaction(store, agent_id, agent_dir)
    except Exception as exc:
        logger.error("run_pipeline: compactor failed, error=%s", exc)
        summary["errors"].append(f"compactor: {exc}")

    # Step 4: strategy analyst (conditional)
    # analyze() returns context string (for agent) or None (bootstrap written)
    try:
        analyst = StrategyAnalyst(agent_dir, store)
        if await analyst.should_run(agent_id):
            await analyst.analyze(agent_id, market_summary="")
            summary["analyst_ran"] = True
    except Exception as exc:
        logger.error("run_pipeline: analyst failed, error=%s", exc)
        summary["errors"].append(f"analyst: {exc}")

    elapsed = round(time.monotonic() - start_time, 2)
    logger.info(
        "run_pipeline: done in %ss, agent_id=%s, errors=%d",
        elapsed, agent_id, len(summary["errors"]),
    )
    return summary


if __name__ == "__main__":
    # Simple CLI: python src/pipeline.py <agent_id> <agent_dir> [db_path]
    # For cron usage without SDK (collector step is skipped)
    logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")

    if len(sys.argv) < 3:
        print("Usage: python src/pipeline.py <agent_id> <agent_dir> [db_path]")
        sys.exit(1)

    _agent_id = sys.argv[1]
    _agent_dir = sys.argv[2]
    _db_path = sys.argv[3] if len(sys.argv) > 3 else "data/bsq.db"

    result = asyncio.run(run_pipeline(_agent_id, _agent_dir, _db_path))
    print(f"Pipeline complete: {result}")
