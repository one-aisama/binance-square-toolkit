---
globs: ["src/db/**"]
---

# Database Rules

- SQLite with WAL mode. No migration system — schema changes via manual ALTER TABLE or DB recreation.
- All tables defined in `src/db/models.py` as `SCHEMA_SQL` string. `init_db()` is idempotent (CREATE TABLE IF NOT EXISTS).
- YAML is the source of truth for account/persona configs. SQLite stores only runtime data (credentials, actions, coordination, parsed data).
- Always use parameterized queries — no f-strings or concatenation in SQL.
- Use `aiosqlite` for all DB operations (async context).
- When adding a new table: add DDL to `SCHEMA_SQL` in `models.py`, no separate migration file needed.
- 10 runtime tables: credentials, actions_log, daily_stats, parsed_trends, parsed_posts, discovered_endpoints, post_tracker, topic_reservations, comment_locks, news_cooldowns.
- 4 operator tables (in src/operator/state_store.py): operator_agents, operator_runs, operator_leases, operator_events.
- DB path: from `DB_PATH` env variable, default `data/bsq.db`.
