# Module: db
# Purpose: SQLite schema and database initialization
# Specification: docs/design-spec.md (Database section)

## Files
| File | Lines | What it does |
|------|-------|--------------|
| database.py | 23 | init_db(db_path) — creates tables via SCHEMA_SQL, WAL mode; get_db_path() from env |
| models.py | 122 | SCHEMA_SQL — DDL for all 10 tables |

## Tables (10)
| Table | Purpose |
|-------|---------|
| credentials | Cookies + headers per account, expiry, valid flag |
| actions_log | Every like/comment/repost/post with status + error |
| daily_stats | Aggregated counters per account per day |
| parsed_trends | Snapshot of topics + fear/greed per parsing cycle |
| parsed_posts | Raw parsed posts for deduplication |
| discovered_endpoints | CDP-discovered bapi endpoints with examples |
| post_tracker | Tracking posts across all agents: ID, type, engagement metrics |
| topic_reservations | Live locks on post topics between agents (2h TTL) |
| comment_locks | Prevents duplicate comments between agents (30min TTL) |
| news_cooldowns | Cooldown on news: 30min hard block + 60min soft penalty |

## Dependencies
- No internal imports
- Used by: `session.credential_store`, `accounts.limiter`, `runtime.comment_coordination`, `runtime.news_cooldown`, `runtime.topic_reservation`

## Key Functions
- `init_db(db_path)` — idempotent (CREATE TABLE IF NOT EXISTS), safe on restart
- `get_db_path()` — reads DB_PATH env var, defaults to "data/bsq.db"

## Common Tasks
- Add a table: DDL in SCHEMA_SQL in `models.py`, call init_db (idempotent)
- Change DB path: DB_PATH environment variable
- Browse data: `sqlite3 data/bsq.db` — WAL mode, reads are non-blocking

## Known Issues
- No migration system — schema changes via manual ALTER TABLE or DB recreation
