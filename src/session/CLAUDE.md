# Module: session
# Purpose: AdsPower browser management, CDP automation, credential capture and storage
# Specification: docs/specs/spec_session.md

## Files
| File | Lines | What it does |
|------|-------|------------|
| adspower.py | 107 | AdsPowerClient — start/stop browser profiles via Local API |
| harvester.py | 122 | harvest_credentials() — navigate to Square via CDP, capture cookies + bapi headers |
| credential_store.py | 80 | CredentialStore — SQLite CRUD for credentials (save, load, invalidate, is_expired) |
| validator.py | 58 | validate_credentials() — test bapi request to check liveness |
| browser_actions.py | ~600 | All Playwright actions: create_post, create_article, repost, comment_on_post, follow_author, collect_feed_posts |
| page_map.py | 79 | CSS selectors and Binance Square URLs (updated 2026-03-24) |

## Dependencies
- Uses: `db` (CredentialStore reads/writes the credentials table)
- Used by: `bapi` (BapiClient loads credentials from CredentialStore)
- Used by: `activity` (browser_actions for comments/reposts via CDP)
- Used by: `scheduler` (harvesting, validation, browser_actions calls)

## Key Functions
- `AdsPowerClient.start_browser(user_id)` — returns `{ws, debug_port, webdriver}`
- `harvest_credentials(ws_endpoint)` — returns `{cookies, headers, discovered_endpoints}`
- `CredentialStore.save/load/invalidate/is_expired(account_id)` — credential lifecycle
- `validate_credentials(cookies, headers)` — returns bool
- `create_post(ws_endpoint, text, coin, sentiment, image_path)` — publish via Playwright
- `comment_on_post(ws_endpoint, post_id, comment_text)` — handles "Follow & Reply" popup
- `collect_feed_posts(ws_endpoint, count, tab)` — collect posts from feed for the agent

## Common Tasks
- Add a selector: edit `page_map.py`, use in `browser_actions.py`
- Add a browser action: add function to `browser_actions.py`, use `_get_page()` pattern
- Debug credential expiration: `credential_store.py` `is_expired()`, `validator.py`

## Known Issues
- `browser_actions.py` is 652 lines, needs splitting when adding new actions
- Selectors in `page_map.py` break when Binance Square UI updates
