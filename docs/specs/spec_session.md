# Specification: Session Module

**Path:** `src/session/`
**Files:** `adspower.py`, `harvester.py`, `credential_store.py`, `credential_crypto.py`, `validator.py`, `browser_actions.py`, `browser_engage.py`, `browser_data.py`, `page_map.py`, `web_visual.py`

---

## Description

The Session module manages all browser infrastructure: starting and stopping AdsPower profiles via the local API, harvesting Binance session credentials (cookies + headers) through Playwright CDP, storing credentials in SQLite, validating their liveness, and performing browser actions (posting, commenting, reposting, following) that cannot be done via regular HTTP because Binance requires a client-side signature (nonce + signature) and DOM input for content creation.

---

## User Stories

- As an agent, I want to start an AdsPower profile for a specific account, so I get a WebSocket endpoint for Playwright connection.
- As an agent, I want to harvest cookies and bapi headers from a live browser session, so BapiClient can make authenticated httpx requests without a browser.
- As an agent, I want to save and load harvested credentials between restarts, so I don't have to re-harvest them every time.
- As an agent, I want to check whether saved credentials are still alive before making bapi calls, so I can detect expiration and re-harvest proactively.
- As an agent, I want to create a post, comment, follow, or repost through browser automation, to perform actions that require Binance's client-side nonce/signature.
- As an agent, I want to browse the recommended feed and interact with posts (like + comment + follow) in a single browser session, to efficiently run a full activity cycle.

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
| `__init__` | `(base_url="http://local.adspower.net:50325", timeout_start=60.0, timeout_stop=30.0, timeout_status=20.0, retry_attempts=2, retry_backoff=0.5)` | -- | All timeouts in seconds |
| `get_status` | `() -> dict` | AdsPower status payload | Raises `AdsPowerError` if unavailable |
| `start_browser` | `(user_id: str) -> dict` | `{"ws": str, "debug_port": str, "webdriver": str}` | `ws` is the CDP endpoint for Playwright |
| `stop_browser` | `(user_id: str) -> dict` | AdsPower stop response | |

**Errors:** `AdsPowerError` -- raised on HTTP error, non-zero `code` in response, or retry exhaustion. Retry uses exponential backoff: `retry_backoff * 2^(attempt-1)`.

---

### harvest_credentials (`src/session/harvester.py`)

```python
async def harvest_credentials(ws_endpoint: str) -> dict[str, Any]
```

Connects via CDP to the browser at `ws_endpoint`, navigates to `https://www.binance.com/en/square`, intercepts all `/bapi/` network responses, and extracts the following headers: `csrftoken`, `bnc-uuid`, `device-info`, `clienttype`, `lang`, `bnc-location`, `bnc-time-zone`, `fvideo-id`, `fvideo-token`, `versioncode`, `x-passthrough-token`, `x-trace-id`, `x-ui-request-trace`, plus `user-agent` from `navigator.userAgent`.

**Returns:**
```python
{
    "cookies": dict[str, str],           # binance.com cookies only
    "headers": dict[str, str],           # all harvested bapi headers
    "discovered_endpoints": list[dict],  # [{"method": str, "path": str}]
}
```

**Raises:** `RuntimeError` on CDP connection failure. Navigation errors are logged as warnings and do not interrupt execution -- partial data is returned.

**Important:** Does NOT close the browser. Browser lifecycle is managed by AdsPower.

---

### CredentialStore (`src/session/credential_store.py`)

| Method | Signature | Returns |
|--------|-----------|---------|
| `__init__` | `(db_path: str)` | -- |
| `save` | `(account_id: str, cookies: dict, headers: dict, max_age_hours: float = 12.0) -> None` | Upsert -- overwrites existing row |
| `load` | `(account_id: str) -> dict \| None` | `{account_id, cookies, headers, harvested_at, expires_at, valid}` or `None` |
| `invalidate` | `(account_id: str) -> None` | Sets `valid = FALSE` |
| `is_valid` | `(account_id: str) -> bool` | `True` if row exists and `valid == TRUE` |
| `is_expired` | `(account_id: str) -> bool` | `True` if `expires_at < utcnow()` or row is missing |

---

### validate_credentials (`src/session/validator.py`)

```python
async def validate_credentials(cookies: dict[str, str], headers: dict[str, str]) -> bool
```

Makes a POST to `https://www.binance.com/bapi/composite/v1/friendly/pgc/card/fearGreedHighestSearched` with the provided cookies and a subset of headers (`csrftoken`, `bnc-uuid`, `device-info`, `user-agent`, `bnc-location`). Returns `True` if the response is HTTP 200 and `data.success == True` or `data.code == "000000"`. Returns `False` on any error or non-auth response.

---

### browser_actions (`src/session/browser_actions.py`)

All functions support two connection modes:
- **Temporary page:** pass `ws_endpoint` -- the function connects via CDP itself and closes in `finally`
- **Persistent page (v3):** pass `page=<Playwright Page>` -- uses an existing page from the SDK session (no reconnection)

In v3 runtime, the SDK holds a persistent page for the entire session. All functions are called with `page=self._page`.

| Function | Signature | Returns |
|----------|-----------|---------|
| `create_post` | `(ws_endpoint=None, text="", coin=None, sentiment=None, image_path=None, *, page=None) -> dict` | `{"success": bool, "post_id": str, ...}` |
| `create_article` | `(ws_endpoint=None, title="", body="", cover_path=None, image_paths=None, *, page=None) -> dict` | `{"success": bool, "post_id": str, ...}` |
| `repost` | `(ws_endpoint=None, post_id="", comment="", *, page=None) -> dict` | `{"success": bool, "original_post_id": str}` |
| `comment_on_post` | `(ws_endpoint=None, post_id="", comment_text="", *, page=None, allow_follow_reply=True) -> dict` | `{"success": bool, "post_id": str, "followed": bool}` |
| `like_post` | `(ws_endpoint=None, post_id="", *, page=None) -> dict` | `{"success": bool, "post_id": str, "already_liked": bool}` |
| `follow_author` | `(ws_endpoint=None, post_id="", *, page=None) -> dict` | `{"success": bool, "post_id": str, "action": str}` |
| `engage_post` | `(ws_endpoint=None, post_id="", like=True, comment_text=None, follow=False, *, page=None, allow_follow_reply=True) -> dict` | `{"success": bool, "actions": dict}` |

> **`browse_and_interact()` was removed** in v3 (2026-03-27). The agent decides what to do on its own -- the SDK only executes. Spam filtering is in `src/strategy/feed_filter.py`. Delays are in `src/runtime/behavior.py`.

**Parameters:**
- `coin`: ticker string (`"BTC"`, `"ETH"`). `sentiment`: `"bullish"` or `"bearish"`.
- `allow_follow_reply`: allow auto-follow on "Follow & Reply" popup (default True).
- `action` in `follow_author`: `"followed"`, `"already_following"`, `"skipped"`.

---

### page_map (`src/session/page_map.py`)

Constants only -- no functions. CSS selectors and URL templates used by `browser_actions`. Key selectors:

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
[missing] -> harvest_credentials() -> save() -> [valid, not expired]
[valid, not expired] -> is_expired() == True -> harvest_credentials() -> save() -> [valid, refreshed]
[valid] -> bapi returns 401/403 -> invalidate() -> [invalid]
[invalid] -> harvest_credentials() -> save() -> [valid]
```

### Hashtag Autocomplete Handling
When typing post text containing `#hashtag`, the Binance autocomplete popup blocks the Post button. `_type_with_hashtag_handling()` splits the text by `#`, types each hashtag word, then presses `Escape` to close the popup before continuing.

### Follow Safety Rule
`follow_author` reads the button's `text_content()`. If the text is `"Following"` or `"Unfollow"`, the click is **not** performed (clicking would unfollow). Clicks only if the text is exactly `"Follow"`.

### Post Button Disambiguation
Two Post buttons exist on the Square page: `.news-post-button` (left panel, opens a modal) and the inline publish button. The inline button is always used: `button[data-bn-type='button']:not(.news-post-button):has-text('Post')`.

### ~~Spam Filtering~~ (moved in v3)
> In v3, spam filtering is in `src/strategy/feed_filter.py`. Human-like delays are in `src/runtime/behavior.py`. The old `browse_and_interact` logic has been removed.

### Validation Headers
`fvideo-id` and `fvideo-token` are required for bapi to return non-null `data`. Without them, bapi returns `data: null` even with HTTP 200.

---

## Edge Cases

| Scenario | Expected Behavior |
|----------|-------------------|
| AdsPower is not running | `AdsPowerError` raised after `retry_attempts` with exponential backoff |
| CDP connection failed | `RuntimeError` from `harvest_credentials` |
| Navigation to Square times out | Warning logged, partial credentials returned (whatever was intercepted before timeout) |
| No bapi requests intercepted | `cookies` dict returned from browser storage; `headers` may be empty or partial |
| Credentials expired (is_expired=True) | Caller must re-harvest; `CredentialStore` does not auto-refresh |
| "Follow & Reply" popup appears when commenting | Popup is clicked -- this simultaneously follows the author AND submits the original comment. A second comment is not written. |
| Post button not found within 5 seconds | `TimeoutError` propagated, `create_post` returns `{"success": False, "error": str}` |
| Persistent page lost (navigation/crash) | SDK reconnects via `_reconnect_page()` or returns an error |
| `create_article` -- not live-tested | May silently fail; the article publish button needs to be scrolled into view before clicking |

---

## Priority and Dependencies

- **Priority:** High (foundational -- all other modules depend on it)
- **Depends on:** `src/db/` (SQLite schema must be initialized before `CredentialStore` can write)
- **Blocks:** `src/bapi/` (BapiClient needs `CredentialStore`), `src/content/publisher.py` (needs `browser_actions`), `src/activity/executor.py` (needs `browser_actions` for comments/reposts)

---

## Additional Modules (added in v3)

### credential_crypto.py (81 lines)
Wrapper for encrypting/decrypting credentials before saving to SQLite. Used by `CredentialStore` transparently.

### browser_data.py (688 lines) -- Read-only DOM Parsing
Data extraction from the DOM without performing actions.

| Function | Purpose |
|----------|---------|
| `collect_feed_posts(ws, count, tab)` | Scrolls the feed, extracts post cards from the DOM in a single pass (without navigating to each post) |
| `get_user_profile(ws, username)` | Parses profile stats from body text |
| `get_post_comments(ws, post_id, limit)` | Extracts comment cards |
| `get_my_comment_replies(ws, username, max_replies)` | Profile Replies tab -> navigates to each post -> collects replies |
| `get_post_stats(ws, post_id)` | Engagement metrics (likes, comments, quotes) |
| `get_my_stats(ws)` | Parses Creator Center dashboard |

### web_visual.py (244 lines) -- Visual Utilities
Utilities for working with page visual elements: color detection, element inspection.

### sdk_screenshot.py (SDKScreenshotMixin) -- Screenshots and Charts
Mixin for SDK. Provides screenshot capture methods via persistent page.

| Method | Signature | Purpose |
|--------|-----------|---------|
| `take_screenshot` | `(url, selector=None, crop=None, wait=5) -> str` | Screenshot of a page or element. Returns file path. |
| `capture_targeted_screenshot` | `(url, *, selectors=None, text_anchors=None, required_texts=None, wait=5) -> str` | Captures a meaningful page fragment (by selectors and text anchors) |
| `screenshot_chart` | `(symbol="BTC_USDT", timeframe="1D") -> str` | Binance chart screenshot (desktop trade view, 16:9) |

Used by `VisualPipeline` from runtime for `chart_capture` and `page_capture` visual kinds.
