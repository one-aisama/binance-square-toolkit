"""Production entry point for the operator control plane.

Usage:
    python scripts/run_operator.py
    python scripts/run_operator.py --max-slots 6
"""

import argparse
import asyncio
import logging
import signal
import sys

from dotenv import load_dotenv

from src.operator.loop import OperatorLoop
from src.operator.models import OperatorConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Binance Square operator control plane.")
    parser.add_argument("--max-slots", type=int, default=4, help="Max concurrent browser slots (default: 4)")
    parser.add_argument("--tick-interval", type=int, default=5, help="Tick interval in seconds (default: 5)")
    parser.add_argument("--persona-mode", default="cli", choices=["cli"], help="Persona bridge mode (default: cli)")
    return parser


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )


async def main_async(args: argparse.Namespace) -> int:
    load_dotenv()

    config = OperatorConfig(
        max_slots=args.max_slots,
        tick_interval_sec=args.tick_interval,
        persona_bridge_mode=args.persona_mode,
    )

    operator = OperatorLoop(config=config)

    # Graceful shutdown on SIGINT/SIGTERM
    def signal_handler():
        asyncio.get_running_loop().create_task(operator.stop())

    try:
        asyncio.get_running_loop().add_signal_handler(signal.SIGINT, signal_handler)
        asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, signal_handler)
    except NotImplementedError:
        pass  # Windows — handled via KeyboardInterrupt below

    try:
        await operator.run()
    except KeyboardInterrupt:
        await operator.stop()

    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    setup_logging()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
