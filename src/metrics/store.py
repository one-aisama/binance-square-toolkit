"""Metrics store — SQLite tables for actions, outcomes, insights, and session stats.

Extends the existing database with tables for the metrics pipeline:
- actions: every agent action with metadata
- outcomes: delayed metrics collected 6h/24h after action
- insights: aggregated scores by dimension (author, content_type, hour, topic)
- profile_snapshots: daily follower/view snapshots
- session_stats: per-session efficiency tracking
"""

import json
import logging
from datetime import datetime
from typing import Any

import aiosqlite

logger = logging.getLogger("bsq.metrics.store")


METRICS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS agent_actions (
    id INTEGER PRIMARY KEY,
    agent_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    target_id TEXT,
    target_author TEXT,
    target_author_followers INTEGER,
    topic TEXT,
    content_type TEXT,
    has_image BOOLEAN DEFAULT FALSE,
    timestamp_utc TEXT NOT NULL,
    success BOOLEAN NOT NULL,
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_agent_actions_session
    ON agent_actions(agent_id, session_id);
CREATE INDEX IF NOT EXISTS idx_agent_actions_type_time
    ON agent_actions(agent_id, action_type, timestamp_utc);

CREATE TABLE IF NOT EXISTS outcomes (
    id INTEGER PRIMARY KEY,
    action_id INTEGER NOT NULL REFERENCES agent_actions(id),
    collected_at TEXT NOT NULL,
    hours_after INTEGER NOT NULL,
    views INTEGER,
    likes INTEGER,
    comments INTEGER,
    quotes INTEGER,
    author_replied BOOLEAN,
    other_replies INTEGER,
    status TEXT NOT NULL DEFAULT 'collected',
    reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_outcomes_action
    ON outcomes(action_id);

CREATE TABLE IF NOT EXISTS insights (
    id INTEGER PRIMARY KEY,
    agent_id TEXT NOT NULL,
    dimension TEXT NOT NULL,
    dimension_value TEXT NOT NULL,
    sample_count INTEGER DEFAULT 0,
    avg_views REAL,
    avg_likes REAL,
    avg_comments REAL,
    author_reply_rate REAL,
    last_updated TEXT,
    UNIQUE(agent_id, dimension, dimension_value)
);

CREATE TABLE IF NOT EXISTS profile_snapshots (
    agent_id TEXT NOT NULL,
    date TEXT NOT NULL,
    followers INTEGER,
    following INTEGER,
    total_views INTEGER,
    total_likes INTEGER,
    PRIMARY KEY (agent_id, date)
);

CREATE TABLE IF NOT EXISTS session_stats (
    session_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    duration_seconds INTEGER,
    planned_actions INTEGER,
    executed_actions INTEGER,
    successful_actions INTEGER,
    failed_actions INTEGER,
    circuits_opened TEXT,
    efficiency REAL
);
CREATE INDEX IF NOT EXISTS idx_session_stats_agent
    ON session_stats(agent_id, started_at);
"""


async def init_metrics_tables(db_path: str) -> None:
    """Create metrics tables if they don't exist. Idempotent."""
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(METRICS_SCHEMA_SQL)
        await db.commit()
    logger.info("Metrics tables initialized")


class MetricsStore:
    """CRUD operations for metrics tables."""

    def __init__(self, db_path: str):
        self._db_path = db_path

    @property
    def db_path(self) -> str:
        return self._db_path

    async def record_action(
        self,
        agent_id: str,
        session_id: str,
        action_type: str,
        success: bool,
        target_id: str | None = None,
        target_author: str | None = None,
        target_author_followers: int | None = None,
        topic: str | None = None,
        content_type: str | None = None,
        has_image: bool = False,
        error_message: str | None = None,
    ) -> int:
        """Record an agent action. Returns the action id."""
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "INSERT INTO agent_actions "
                "(agent_id, session_id, action_type, target_id, target_author, "
                "target_author_followers, topic, content_type, has_image, "
                "timestamp_utc, success, error_message) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    agent_id, session_id, action_type, target_id, target_author,
                    target_author_followers, topic, content_type, has_image,
                    now, success, error_message,
                ),
            )
            await db.commit()
            return cursor.lastrowid

    async def record_outcome(
        self,
        action_id: int,
        hours_after: int,
        views: int | None = None,
        likes: int | None = None,
        comments: int | None = None,
        quotes: int | None = None,
        author_replied: bool | None = None,
        other_replies: int | None = None,
        status: str = "collected",
        reason: str | None = None,
    ) -> None:
        """Record delayed outcome for an action."""
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO outcomes "
                "(action_id, collected_at, hours_after, views, likes, comments, "
                "quotes, author_replied, other_replies, status, reason) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    action_id, now, hours_after, views, likes, comments,
                    quotes, author_replied, other_replies, status, reason,
                ),
            )
            await db.commit()

    async def get_actions_without_outcomes(
        self, agent_id: str, min_hours_old: int = 6
    ) -> list[dict[str, Any]]:
        """Get actions older than min_hours_old that have no outcome yet."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT a.* FROM agent_actions a "
                "LEFT JOIN outcomes o ON a.id = o.action_id "
                "WHERE a.agent_id = ? AND a.success = 1 "
                "AND o.id IS NULL "
                "AND a.timestamp_utc <= datetime('now', ? || ' hours') "
                "ORDER BY a.timestamp_utc",
                (agent_id, f"-{min_hours_old}"),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def upsert_insight(
        self,
        agent_id: str,
        dimension: str,
        dimension_value: str,
        sample_count: int,
        avg_views: float | None = None,
        avg_likes: float | None = None,
        avg_comments: float | None = None,
        author_reply_rate: float | None = None,
    ) -> None:
        """Insert or update an insight row."""
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO insights "
                "(agent_id, dimension, dimension_value, sample_count, "
                "avg_views, avg_likes, avg_comments, author_reply_rate, last_updated) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(agent_id, dimension, dimension_value) DO UPDATE SET "
                "sample_count = ?, avg_views = ?, avg_likes = ?, "
                "avg_comments = ?, author_reply_rate = ?, last_updated = ?",
                (
                    agent_id, dimension, dimension_value, sample_count,
                    avg_views, avg_likes, avg_comments, author_reply_rate, now,
                    sample_count, avg_views, avg_likes, avg_comments,
                    author_reply_rate, now,
                ),
            )
            await db.commit()

    async def get_insights(
        self, agent_id: str, dimension: str | None = None
    ) -> list[dict[str, Any]]:
        """Get insights, optionally filtered by dimension."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            if dimension:
                cursor = await db.execute(
                    "SELECT * FROM insights WHERE agent_id = ? AND dimension = ? "
                    "ORDER BY sample_count DESC",
                    (agent_id, dimension),
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM insights WHERE agent_id = ? "
                    "ORDER BY dimension, sample_count DESC",
                    (agent_id,),
                )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def save_profile_snapshot(
        self,
        agent_id: str,
        followers: int,
        following: int,
        total_views: int = 0,
        total_likes: int = 0,
    ) -> None:
        """Save daily profile snapshot. One per agent per day."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO profile_snapshots "
                "(agent_id, date, followers, following, total_views, total_likes) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(agent_id, date) DO UPDATE SET "
                "followers = ?, following = ?, total_views = ?, total_likes = ?",
                (
                    agent_id, today, followers, following, total_views, total_likes,
                    followers, following, total_views, total_likes,
                ),
            )
            await db.commit()

    async def save_session_stats(
        self,
        session_id: str,
        agent_id: str,
        started_at: str,
        ended_at: str,
        planned_actions: int,
        executed_actions: int,
        successful_actions: int,
        failed_actions: int,
        circuits_opened: list[str],
        efficiency: float,
    ) -> None:
        """Save session stats after session completes."""
        duration = 0
        try:
            start = datetime.fromisoformat(started_at)
            end = datetime.fromisoformat(ended_at)
            duration = int((end - start).total_seconds())
        except (ValueError, TypeError):
            pass

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO session_stats "
                "(session_id, agent_id, started_at, ended_at, duration_seconds, "
                "planned_actions, executed_actions, successful_actions, "
                "failed_actions, circuits_opened, efficiency) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id, agent_id, started_at, ended_at, duration,
                    planned_actions, executed_actions, successful_actions,
                    failed_actions, json.dumps(circuits_opened), efficiency,
                ),
            )
            await db.commit()

    async def get_session_history(
        self, agent_id: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Get recent session stats for an agent."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM session_stats WHERE agent_id = ? "
                "ORDER BY started_at DESC LIMIT ?",
                (agent_id, limit),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_total_sessions(self, agent_id: str) -> int:
        """Count total sessions for bootstrap detection."""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM session_stats WHERE agent_id = ?",
                (agent_id,),
            )
            return (await cursor.fetchone())[0]
