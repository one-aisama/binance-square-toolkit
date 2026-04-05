# Specification: Bapi Client Module

**Path:** `src/bapi/`
**Files:** `client.py`, `endpoints.py`, `models.py`

---

## Description

The Bapi module is the single HTTP gateway between the toolkit and Binance's internal bapi API. It injects harvested credentials (cookies + headers) into every request, enforces per-account rate limiting, retries on transient errors, and automatically invalidates credentials on authentication failures. It also provides typed Pydantic models for bapi responses and a central constants file with all known endpoint paths.

---

## User Stories

- As an agent, I want to call `get_feed_recommend()`, `get_top_articles()`, `get_fear_greed()`, and `get_hot_hashtags()` without manually managing HTTP headers, so I can focus on data processing.
- As an agent, I want bapi requests to automatically use the correct credentials for a specific account, so I can work with multiple accounts without confusion.
- As an agent, I want failed requests due to rate limiting or server errors to be automatically retried, so transient failures don't interrupt the session.
- As an agent, I want authentication errors (HTTP 401/403) to immediately invalidate credentials and return a clear error, so I know to re-harvest credentials rather than keep retrying.
- As an agent, I want a central endpoint constants file, so I never hardcode paths in business logic.

---

## Data Model

No dedicated tables. `BapiClient` reads from the `credentials` table via `CredentialStore`. It does not write anything itself.

Pydantic models in `src/bapi/models.py`:

### BapiResponse
```python
class BapiResponse(BaseModel):
    code: str = ""          # "000000" = success
    message: str | None = None
    data: Any = None
    success: bool = False

    @property
    def is_ok(self) -> bool: ...  # code == "000000" or success == True
```

### FeedPost
```python
class FeedPost(BaseModel):
    post_id: str = ""
    author_name: str = ""
    author_role: str = ""
    card_type: str = ""
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    hashtags: list[str] = []
    trading_pairs: list[str] = []
    is_ai_created: bool = False
    created_at: int = 0     # Unix timestamp ms
    text_preview: str = ""
```

---

## API

### BapiClient (`src/bapi/client.py`)

```python
class BapiClient:
    def __init__(
        self,
        account_id: str,
        credential_store: CredentialStore,
        base_url: str = "https://www.binance.com",
        rate_limit_rpm: int = 30,
        retry_attempts: int = 3,
        retry_backoff: float = 1.0,
    )
```

`rate_limit_rpm` is converted to `min_interval = 60 / rate_limit_rpm` seconds between requests.

#### Low-Level Methods

| Method | Signature | Returns |
|--------|-----------|---------|
| `get` | `(path: str, params: dict \| None = None) -> dict` | Raw bapi response dict |
| `post` | `(path: str, data: dict \| None = None) -> dict` | Raw bapi response dict |

Both delegate to `_request(method, path, params, json_data)`, which:
1. Applies rate limiting (sleeps if `elapsed < min_interval`)
2. Loads credentials via `CredentialStore.load(account_id)`
3. Assembles headers: `content-type: application/json`, serialized `cookie` string, then all harvested headers
4. Executes the request via `httpx.AsyncClient`, timeout=30s
5. On HTTP 401/403: calls `CredentialStore.invalidate()`, raises `BapiCredentialError`
6. On HTTP 429/500/502/503: retries up to `retry_attempts` with exponential backoff (`retry_backoff * 2^(attempt-1)`)
7. On `httpx.TimeoutException` / `httpx.NetworkError`: retries similarly

#### Convenience Parsing Methods

| Method | Signature | Returns |
|--------|-----------|---------|
| `get_feed_recommend` | `(page: int = 1, page_size: int = 20) -> list[dict]` | Posts from `data.vos` or `data.list` |
| `get_top_articles` | `(page: int = 1, page_size: int = 20) -> list[dict]` | Articles from `data.vos` or `data.list` |
| `get_fear_greed` | `() -> dict` | Fear/greed data from `data` |
| `get_hot_hashtags` | `() -> list[dict]` | Hashtag list from `data` |
| `like_post` | `(post_id: str, card_type: str = "BUZZ_SHORT") -> dict` | Raw bapi response |

#### Stub Methods (not implemented)

| Method | Raises |
|--------|--------|
| `create_post(text, hashtags)` | `NotImplementedError` -- use `browser_actions.create_post()` |
| `comment_post(post_id, text)` | `NotImplementedError` -- use `browser_actions.comment_on_post()` |
| `repost(post_id)` | `NotImplementedError` -- use `browser_actions.repost()` |

---

### Endpoints (`src/bapi/endpoints.py`)

| Constant | Path | Method |
|----------|------|--------|
| `FEED_RECOMMEND` | `/bapi/composite/v9/friendly/pgc/feed/feed-recommend/list` | POST |
| `TOP_ARTICLES` | `/bapi/composite/v3/friendly/pgc/content/article/list` | GET |
| `FEAR_GREED` | `/bapi/composite/v1/friendly/pgc/card/fearGreedHighestSearched` | POST |
| `HOT_HASHTAGS` | `/bapi/composite/v2/public/pgc/hashtag/hot-list` | GET |
| `CONTENT_PRE_CHECK` | `/bapi/composite/v1/private/pgc/content/pre-check` | POST |
| `CREATOR_CONTENT_LIST` | `/bapi/composite/v5/private/pgc/creator/content/list` | POST |
| `DRAFT_COUNT` | `/bapi/composite/v1/private/pgc/content/draft/count` | POST |
| `USER_PROFILE` | `/bapi/composite/v4/private/pgc/user` | GET |
| `SUGGESTED_CREATORS` | `/bapi/composite/v1/friendly/pgc/suggested/creator/list` | POST |
| `LIKE_POST` | `/bapi/composite/v1/private/pgc/content/like` | POST |

Endpoints for comments and reposts have not been discovered yet.

---

## Business Logic

### Request Body for FEED_RECOMMEND
Must contain `scene: "web-homepage"` and `contentIds: []` in the POST body, otherwise the endpoint returns empty results. Response data is in `data.vos`, not `data.list`.

### Fear & Greed Is a POST, Not GET
`FEAR_GREED` requires a `POST` with an empty JSON body `{}`. A `GET` request returns an error.

### Like Request Body
`LIKE_POST` requires `{"id": "<post_id>", "cardType": "BUZZ_SHORT"}`. The `cardType` field is mandatory.

### fvideo Headers Are Required
Without `fvideo-id` and `fvideo-token` in request headers, bapi returns `data: null` even with HTTP 200. They must be present in the harvested headers.

### Credential Injection Flow
```
_request() called
  -> CredentialStore.load(account_id)
  -> if None -> raise BapiCredentialError
  -> assemble cookie string from cookies dict
  -> copy all harvested headers (except "cookie") into request_headers
  -> execute httpx request
  -> if 401/403 -> CredentialStore.invalidate() -> raise BapiCredentialError
  -> if retryable status -> retry with backoff
  -> return parsed JSON dict
```

### Rate Limiting
`_last_request_time` is an instance variable. Each request checks `time.monotonic() - _last_request_time` and sleeps if the interval hasn't elapsed. This is per-instance (per-account), not global.

---

## Edge Cases

| Scenario | Expected Behavior |
|----------|-------------------|
| `CredentialStore.load()` returns None | `BapiCredentialError` raised immediately, no HTTP request made |
| HTTP 401 or 403 | Credentials invalidated via `CredentialStore.invalidate()`, `BapiCredentialError` raised |
| HTTP 429 (rate limit from Binance) | Retries up to `retry_attempts` with exponential backoff, then raises `BapiRequestError` |
| HTTP 500/502/503 | Same retry behavior as 429 |
| Network timeout | `BapiRequestError` after `retry_attempts` retries |
| `data.vos` and `data.list` both missing from response | Returns an empty list `[]` |
| `get_fear_greed` returns non-dict `data` | Returns an empty dict `{}` |
| `get_hot_hashtags` returns non-list `data` | Returns an empty list `[]` |
| `like_post` called with a non-existent post_id | Bapi returns an error code in the response body; raw dict is returned, no exception |

---

## Priority and Dependencies

- **Priority:** High
- **Depends on:** `src/session/credential_store.py` (must be initialized before creating `BapiClient`), `src/db/` (SQLite schema for the credentials table)
- **Blocks:** `src/parser/fetcher.py` (TrendFetcher), `src/activity/executor.py` (like_post)
