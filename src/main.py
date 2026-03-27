"""Binance Square Content Farm — Main Entry Point."""

import asyncio
import signal
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

import yaml
from dotenv import load_dotenv

from src.db.database import init_db, get_db_path
from src.accounts.manager import load_accounts
from src.scheduler.scheduler import CycleScheduler

logger = logging.getLogger("bsq")


def setup_logging():
    """Configure logging with stdout + rotating file handlers."""
    log_level = os.environ.get("LOG_LEVEL", "INFO")
    log_dir = os.environ.get("LOG_DIR", "logs/")
    os.makedirs(log_dir, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s", datefmt="%H:%M:%S")

    # Stdout handler
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    stdout_handler.setFormatter(fmt)
    root.addHandler(stdout_handler)

    # Main log file
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "bsq.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    # Error-only log file
    error_handler = RotatingFileHandler(
        os.path.join(log_dir, "bsq_errors.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(fmt)
    root.addHandler(error_handler)


def load_settings(path: str = "config/settings.yaml") -> dict:
    """Load global settings from YAML."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


async def main():
    """Main async entry point."""
    load_dotenv()
    setup_logging()

    logger.info("=" * 50)
    logger.info("Binance Square Content Farm starting...")
    logger.info("=" * 50)

    # Load settings
    settings = load_settings()
    logger.info(f"Settings loaded: {len(settings)} keys")

    # Init database
    db_path = get_db_path()
    await init_db(db_path)
    logger.info(f"Database initialized at {db_path}")

    # Load accounts
    accounts = load_accounts("config/accounts", "config/personas.yaml")
    logger.info(f"Loaded {len(accounts)} accounts")

    if not accounts:
        logger.warning("No accounts configured. Add YAML files to config/accounts/")
        logger.info("Create a config from config/accounts/_example.yaml")
        # Continue anyway — scheduler will run but skip processing

    # Start scheduler
    scheduler = CycleScheduler(settings, accounts, db_path)
    scheduler.start()

    # Wait for shutdown signal (Windows-compatible)
    stop_event = asyncio.Event()

    def handle_signal(signum, frame):
        logger.info(f"Shutdown signal received (signal {signum})")
        stop_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        await stop_event.wait()
    except KeyboardInterrupt:
        pass

    logger.info("Shutting down...")
    scheduler.stop()
    logger.info("Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
