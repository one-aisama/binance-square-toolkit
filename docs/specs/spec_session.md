# Specification: Session Module

**Path:** `src/session/`
**Files:** `adspower.py`, `harvester.py`, `credential_store.py`, `validator.py`, `browser_actions.py`, `page_map.py`

---

## Description

The Session module manages all browser infrastructure: starting and stopping AdsPower profiles via the local API, capturing Binance session credentials (cookies + headers) via Playwright CDP, storing credentials in SQLite, validating their liveness, and executing browser actions (posting, commenting, reposting, following) that cannot be performed via regular HTTP because Binance requires a client-side signature (nonce + signature) and DOM input for content creation.

---

## User Stories

- As an agent, I want to start an AdsPower profile for a specific account, so I get a WebSocket endpoint for Playwright connection.
- As an agent, I want to capture cookies and bapi headers from a live browser session, so BapiClient can make authenticated httpx requests without a browser.
- As an agent, I want to save and load captured credentials between restarts, so I don't have to recapture them every time.
- As an agent, I want to check whether saved credentials are still live before making bapi calls, so I can detect expiration and recapture proactively.
- As an agent, I want to create a post, comment, follow, or repost via browser automation, so I can perform actions that require Binance's client-side nonce/signature.
- As an agent, I want to browse the recommended feed and interact with posts (like + comment + follow) in a single browser session, so I can efficiently run a full activity cycle.

---

## Data Model

Credentials are stored in SQLite (defined in `src/db/models.py`):

```sql
CREATE TABLE IF NOT EXISTS credentials (
    account_id TEXT PRIMARY KEY,
    cookies    TEXT NOT NULL,       -- JSON-serialized dict[str, str]
    headers    TEXT NOT NULL,       -- JSON-serialized dict[str, str]
    harvested_at TIMESTAMP NOT NULL,
    expires_at   TIMESTAMP,         -- NULL = no expiry
    valid        BOOLEAN DEFAULT TRUE
);
```

No additional tables. `CredentialStore` is the sole reader/writer of this table.

---

## API

### AdsPowerClient (`src/session/adspower.py`)

| Method | Signature | Returns | Notes |
|--------|-----------|---------|-------|
| `__init__` | `(base_url="http://local.adspower.net:50325", timeout_start=60.0, timeout_stop=30.0, timeout_status=20.0, retry_attempts=2, retry_backoff=0.5)` | — | All timeouts in seconds |
| `get_status` | `() -> dict` | AdsPower status payload | Raises `AdsPowerError` if unavailable |
| `start_browser` | `(user_id: str) -> dict` | `{"ws": str, "debug_port": str, "webdriver": str}` | `ws` is the CDP endpoint for Playwright |
| `stop_browser` | `(user_id: str) -> dict` | AdsPower stop response | |

**Errors:** `AdsPowerError` — raised on HTTP error, non-zero `code` in response, or exhausted retries. Retry uses exponential backoff: `retry_backoff * 2^(attempt-1)`.

---

### harvest_credentials (`src/session/harvester.py`)

```python
async def harvest_credentials(ws_endpoint: str) -> dict[str, Any]
```

Connects via CDP to the browser at `ws_endpoint`, navigates to `https://www.binance.com/en/square`, intercepts all `/bapi/` network responses, extracts the following headers: `csrftoken`, `bnc-uuid`, `device-info`, `clienttype`, `lang`, `bnc-location`, `bnc-time-zone`, `fvideo-id`, `fvideo-token`, `versioncode`, `x-passthrough-token`, `x-trace-id`, `x-ui-request-trace`, plus `user-agent` from `navigator.userAgent`.

**Returns:**
```python
{
    "cookies": dict[str, str],           # binance.com cookies only
    "headers": dict[str, str],           # all captured bapi headers
    "discovered_endpoints": list[dict],  # [{"method": str, "path": str}]
}
```

**Raises:** `RuntimeError` on CDP connection failure. Navigation errors are logged as warnings and don't abort — partial data is returned.

**Important:** Does NOT close the browser. Browser lifecycle is managed by AdsPower.

---

### CredentialStore (`src/session/credential_store.py`)

| Method | Signature | Returns |
|--------|-----------|---------|
| `__init__` | `(db_path: str)` | — |
| `save` | `(account_id: str, cookies: dict, headers: dict, max_age_hours: float = 12.0) -> None` | Upsert — overwrites existing row |
| `load` | `(account_id: str) -> dict \| None` | `{account_id, cookies, headers, harvested_at, expires_at, valid}` or `None` |
| `invalidate` | `(account_id: str) -> None` | Sets `valid = FALSE` |
| `is_valid` | `(account_id: str) -> bool` | `True` if row exists and `valid == TRUE` |
| `is_expired` | `(account_id: str) -> bool` | `True` if `expires_at < utcnow()` or row doesn't exist |

---

### validate_credentials (`src/session/validator.py`)

```python
async def validate_credentials(cookies: dict[str, str], headers: dict[str, str]) -> bool
```

Makes a POST to `https://www.binance.com/bapi/composite/v1/friendly/pgc/card/fearGreedHighestSearched` with the provided cookies and a subset of headers (`csrftoken`, `bnc-uuid`, `device-info`, `user-agent`, `bnc-location`). Returns `True` if the response is HTTP 200 and `data.success == True` or `data.code == "000000"`. Returns `False` on any error or non-auth response.

---

### browser_actions (`src/session/browser_actions.py`)

All functions connect to the browser via `_get_page(ws_endpoint)`, which returns `(playwright, browser, page)` using `context.pages[0]`. All functions call `await pw.stop()` in `finally`.

| Function | Signature | Returns |
|----------|-----------|---------|
| `create_post` | `(ws_endpoint, text, coin=None, sentiment=None, image_path=None) -> dict` | `{"success": bool, "post_id": str, ...}` |
| `create_article` | `(ws_endpoint, title, body, cover_path=None, image_paths=None) -> dict` | `{"success": bool, "post_id": str, ...}` |
| `repost` | `(ws_endpoint, post_id, comment="") -> dict` | `{"success": bool, "original_post_id": str}` |
| `comment_on_post` | `(ws_endpoint, post_id, comment_text) -> dict` | `{"success": bool, "post_id": str, "followed": bool}` |
| `follow_author` | `(ws_endpoint, post_id) -> dict` | `{"success": bool, "post_id": str, "action": str}` |
| `browse_and_interact` | `(ws_endpoint, comment_generator=None, count=5, skip_rate=0.3) -> dict` | `{"success": bool, "interacted": int, "skipped": int, "actions": list}` |

`coin` values for `create_post`: ticker string like `"BTC"`, `"ETH"`. `sentiment`: `"bullish"` or `"bearish"`.

`action` values in `follow_author`: `"followed"`, `"already_following"`, `"skipped"`.

---

### page_map (`src/session/page_map.py`)

Constants only — no functions. CSS selectors and URL templates used by `browser_actions`. Key selectors:

| Constant | Value | Used For |
|----------|-------|----------|
| `SQUARE_URL` | `"https://www.binance.com/en/square"` | Navigation |
| `POST_URL_TEMPLATE` | `"https://www.binance.com/en/square/post/{post_id}"` | Navigation |
| `COMPOSE_EDITOR` | `"div.ProseMirror[contenteditable='true']"` | Text input |
| `COMPOSE_INLINE_POST_BUTTON` | `"button[data-bn-type='button']:not(.news-post-button):has-text('Post')"` | Publishing |
| `POST_REPLY_INPUT` | `'input[placeholder="Post your reply"]'` | Comment input |
| `POST_FOLLOW_REPLY_POPUP` | `"button:has-text('Follow & Reply')"` | Restricted commenting popup |
| `FOLLOW_BUTTON` | `"button:has-text('Follow')"` | Following |

---

## Business Logic

### Credential Lifecycle
```
[absent] → harvest_credentials() → save() → [valid, not expired]
[valid, not expired] → is_expired() == True → harvest_credentials() → save() → [valid, refreshed]
[valid] → bapi returns 401/403 → invalidate() → [invalid]
[invalid] → harvest_credentials() → save() → [valid]
```

### Hashtag Autocomplete Handling
When typing post text containing `#hashtag`, the Binance autocomplete popup blocks the Post button. `_type_with_hashtag_handling()` splits text by `#`, types each hashtag word, then presses `Escape` to close the popup before continuing.

### Follow Safety Rule
`follow_author` reads the button's `text_content()`. If the text is `"Following"` or `"Unfollow"`, the click is **not** performed (clicking would unfollow). Only clicks if the text is exactly `"Follow"`.

### Post Button Disambiguation
The Square page has two Post buttons: `.news-post-button` (left panel, opens a modal) and an inline publish button. The inline button is always used: `button[data-bn-type='button']:not(.news-post-button):has-text('Post')`.

### Spam Filtering in browse_and_interact
Posts are skipped if: text length < 50 characters, likes < 3, or text contains any of `{"gift", "giveaway", "airdrop", "copy trading"}`. Human-like delay between posts: `random.uniform(15, 35) + (interacted_count * 2)` seconds.

### Validation Headers
`fvideo-id` and `fvideo-token` are required for bapi to return non-null `data`. Without them, bapi returns `data: null` even with HTTP 200.

---

## Edge Cases

| Situation | Expected Behavior |
|-----------|-------------------|
| AdsPower not running | `AdsPowerError` raised after `retry_attempts` with exponential backoff |
| CDP connection failed | `RuntimeError` from `harvest_credentials` |
| Navigation to Square times out | Warning logged, partial credentials returned (whatever was intercepted before timeout) |
| No bapi requests intercepted | Browser storage `cookies` dict is returned; `headers` may be empty or partial |
| Credentials expired (is_expired=True) | Caller must recapture; `CredentialStore` does not auto-refresh |
| "Follow & Reply" popup appears during commenting | Popup is clicked — this simultaneously follows the author AND submits the original comment. A second comment is not written. |
| Post button not found within 5 seconds | `TimeoutError` propagated, `create_post` returns `{"success": False, "error": str}` |
| `browse_and_interact` with empty feed | Returns `{"success": True, "interacted": 0, "skipped": 0, "actions": []}` |
| `create_article` — not tested live | May silently fail; the article publish button needs to be scrolled into view before clicking |

---

## Priority and Dependencies

- **Priority:** High (foundational — all other modules depend on it)
- **Depends on:** `src/db/` (SQLite schema must be initialized before `CredentialStore` can write)
- **Blocks:** `src/bapi/` (BapiClient needs `CredentialStore`), `src/content/publisher.py` (needs `browser_actions`), `src/activity/executor.py` (needs `browser_actions` for comments/reposts)
