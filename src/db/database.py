import aiosqlite
import os
import logging

from src.db.models import SCHEMA_SQL

logger = logging.getLogger("bsq.db")


async def init_db(db_path: str) -> None:
    """Initialize SQLite database with WAL mode and create all tables."""
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.executescript(SCHEMA_SQL)
        await db.commit()
    logger.info(f"Database initialized at {db_path}")


def get_db_path() -> str:
    """Get database path from environment or default."""
    return os.environ.get("DB_PATH", "data/bsq.db")
