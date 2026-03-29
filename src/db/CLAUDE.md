# Module: db
# Purpose: SQLite schema and database initialization
# Specification: docs/design-spec.md (Database section)

## Files
| File | Lines | What it does |
|------|-------|------------|
| database.py | 23 | init_db(db_path) — table creation via SCHEMA_SQL, WAL mode; get_db_path() from env |
| models.py | 90 | SCHEMA_SQL — DDL for all tables |

## Tables
| Table | Purpose |
|-------|---------|
| credentials | Cookies + headers per account, expiry, valid flag |
| actions_log | Every like/comment/repost/post with status + error |
| daily_stats | Aggregated counters per account per day |
| content_queue | Generated posts awaiting publication |
| parsed_trends | Snapshot of topics + fear/greed per parsing cycle |
| parsed_posts | Raw parsed posts for deduplication |
| discovered_endpoints | CDP-discovered bapi endpoints with examples |
| post_tracker | Tracking posts of all agents: ID, type, engagement metrics (supervisor) |

## Dependencies
- No internal imports
- Used by: `session.credential_store`, `accounts.limiter`, `content.publisher`, `scheduler`

## Key Functions
- `init_db(db_path)` — idempotent (CREATE TABLE IF NOT EXISTS), safe on restart
- `get_db_path()` — reads DB_PATH env var, defaults to "data/bsq.db"

## Common Tasks
- Add a table: DDL in SCHEMA_SQL in `models.py`, call init_db (idempotent)
- Change DB path: DB_PATH environment variable
- View data: `sqlite3 data/bsq.db` — WAL mode, reads are non-blocking

## Known Issues
- No migration system — schema changes via manual ALTER TABLE or DB recreation
