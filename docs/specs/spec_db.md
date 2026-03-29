# Specification: db
# Module: src/db/
# Status: implemented

## Purpose
SQLite storage for runtime data: credentials, actions, content queue, parsing.
YAML is the source of truth for configs. SQLite is runtime only.

## Files
| File | What it does |
|------|------------|
| database.py | `init_db(db_path)` — idempotent table creation, WAL mode; `get_db_path()` from env |
| models.py | `SCHEMA_SQL` — DDL for all 7 tables |

## Tables

### credentials
Cookies + headers from authorized sessions.
- `account_id` TEXT PK — account identifier
- `cookies` TEXT — JSON cookies from CDP
- `headers` TEXT — JSON headers (csrftoken, fvideo-id, fvideo-token)
- `harvested_at` TIMESTAMP — when captured
- `expires_at` TIMESTAMP — when they expire
- `valid` BOOLEAN — validity flag

### actions_log
Every action (like, comment, repost, post) with status.
- `account_id`, `action_type`, `target_id`, `status`, `error_message`, `created_at`
- Index: `(account_id, action_type, created_at)` — for limit counting

### daily_stats
Aggregated counters per account per day.
- `account_id`, `date`, `posts_count`, `likes_count`, `comments_count`, `reposts_count`, `errors_count`
- UNIQUE: `(account_id, date)`

### content_queue
Generated posts awaiting publication.
- `account_id`, `text`, `hashtags`, `topic`, `generation_meta`, `status`, `scheduled_at`, `published_at`, `post_id`
- Indexes: `(account_id, status)`, `(status, scheduled_at)`

### parsed_trends
Snapshot of topics + fear/greed per parsing cycle.
- `cycle_id`, `topics` (JSON), `fear_greed_index`, `popular_coins`

### parsed_posts
Raw parsed posts for deduplication.
- `cycle_id`, `post_id`, `author_name`, `card_type`, metrics (views, likes, comments, shares), `hashtags`, `trading_pairs`, `is_ai_created`
- UNIQUE: `(cycle_id, post_id)`

### discovered_endpoints
CDP-discovered bapi endpoints with request/response examples.
- `method`, `path`, `purpose`, `request_headers`, `request_body`, `response_sample`
- UNIQUE: `(method, path)`

## Rules
- WAL mode is mandatory
- All queries are parameterized — no f-strings in SQL
- `aiosqlite` for all operations (async)
- New table: add DDL to `SCHEMA_SQL`, call `init_db` (idempotent)
- DB path: `DB_PATH` variable, defaults to `data/bsq.db`

## Known Limitations
- No migration system — changes via ALTER TABLE or DB recreation
