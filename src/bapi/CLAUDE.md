# Module: bapi
# Purpose: HTTP client to Binance bapi — credential injection, rate limiting, retry, convenience methods
# Specification: docs/specs/spec_bapi.md

## Files
| File | Lines | What it does |
|------|-------|------------|
| client.py | 194 | BapiClient — GET/POST with auth headers, 30 RPM limit, retry on 429/5xx, auto-invalidation on 401/403 |
| endpoints.py | 21 | URL constants for all known bapi endpoints (parsing + activity) |
| models.py | 34 | Pydantic models: BapiResponse, FeedPost |

## Dependencies
- Uses: `session.credential_store` (CredentialStore — loading cookies+headers)
- Used by: `parser` (TrendFetcher calls get_feed_recommend, get_top_articles, etc.)
- Used by: `content` (ContentPublisher calls create_post — stub)
- Used by: `activity` (ActivityExecutor calls like_post)
- Used by: `scheduler` (creates BapiClient for each account)

## Key Functions
- `BapiClient(account_id, credential_store, rate_limit_rpm=30)` — constructor
- `BapiClient.get_feed_recommend(page, page_size)` — list of raw posts
- `BapiClient.get_top_articles(page, page_size)` — list of raw articles
- `BapiClient.get_fear_greed()` — fear/greed index + popular coins
- `BapiClient.get_hot_hashtags()` — list of hashtags
- `BapiClient.like_post(post_id, card_type)` — works (endpoint found)

## Common Tasks
- Add endpoint: constant in `endpoints.py`, method in `BapiClient`
- Debug auth errors: check `credential_store.load()`, search for 401/403 in logs

## Known Issues
- `create_post`, `comment_post`, `repost` are stubs (endpoints not found, using browser)
