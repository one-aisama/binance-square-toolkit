---
globs: ["src/db/**"]
---

# Database Rules

- SQLite with WAL mode. No migration system — schema changes via manual ALTER TABLE or DB recreation.
- All tables are defined in `src/db/models.py` as a `SCHEMA_SQL` string. `init_db()` is idempotent (CREATE TABLE IF NOT EXISTS).
- YAML is the source of truth for account/persona configs. SQLite stores only runtime data (credentials, actions, content queue, parsed data).
- Always use parameterized queries — no f-strings or concatenation in SQL.
- Use `aiosqlite` for all DB operations (async context).
- When adding a new table: add DDL to `SCHEMA_SQL` in `models.py`, no separate migration file needed.
- 7 tables: credentials, actions_log, daily_stats, content_queue, parsed_trends, parsed_posts, discovered_endpoints.
- DB path: from the `DB_PATH` variable, defaults to `data/bsq.db`.
