# Specification: Content Module

**Path:** `src/content/`
**Files:** `generator.py`, `publisher.py`, `market_data.py`

---

## Description

The Content module provides tools for AI text generation and content queue management. The agent calls `ContentGenerator.generate()` to create post text in the style of a specific persona, then `ContentPublisher.queue_content()` to save it in SQLite for later publishing. `get_market_data()` fetches real coin prices from the Binance public API so the agent can insert specific numbers into content.

The module does NOT decide what to publish and when. `ContentGenerator` and `ContentPublisher` are tools that the agent calls. The agent analyzes the parser output, selects topics for each persona, and calls these functions to generate and queue content.

---

## User Stories

- As an agent, I want to generate post text in the style of a specific persona with real market data, so each account's content matches its niche and contains specific numbers.
- As an agent, I want to queue generated content for a specific account with optional scheduling, so I can create content in batches and publish later.
- As an agent, I want to get current coin prices (price, 24h change, volume), so I can include accurate data in generated content.
- As an agent, I want to fetch pending content from the queue, so I can publish it via `browser_actions.create_post()`.
- As an agent, I want to mark queue items as published or failed, so I can track the content lifecycle.

---

## Data Model

### Content Queue Table (defined in `src/db/models.py`)

```sql
CREATE TABLE IF NOT EXISTS content_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL,
    text TEXT NOT NULL,
    hashtags TEXT,              -- JSON array
    topic TEXT,
    generation_meta TEXT,       -- JSON dict with generation params
    scheduled_at TEXT,          -- ISO timestamp, NULL = publish immediately
    status TEXT DEFAULT 'pending',  -- pending | published | failed
    post_id TEXT,               -- Binance post ID after publishing
    published_at TEXT,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

No additional tables. The module reads/writes only `content_queue`.

---

## API

### ContentGenerator (`src/content/generator.py`)

```python
class ContentGenerator:
    def __init__(self, provider: str, model: str, api_key: str)
```

| Method | Signature | Returns |
|--------|-----------|---------|
| `generate` | `(persona_style: str, persona_topics: list[str], topic: dict, market_data: dict) -> str` | Generated post text |

**Providers:** `"anthropic"` (Claude API) and `"openai"` (OpenAI API). Provider is selected at instantiation.

**Prompt structure:**
- System prompt: persona style, topic areas, strict writing rules (no AI cliches, conversational tone, $CASHTAGS, etc.)
- User prompt: topic name + trending hashtags + related coins + current market data (prices, 24h change)

The system prompt contains rules from `config/content_rules.yaml` inline (not loaded from file — rules are embedded in the prompt string).

---

### ContentPublisher (`src/content/publisher.py`)

```python
class ContentPublisher:
    def __init__(self, client: BapiClient, db_path: str)
```

| Method | Signature | Returns |
|--------|-----------|---------|
| `publish` | `(text: str, hashtags: list[str] \| None = None) -> dict` | Calls `BapiClient.create_post()` — currently raises `NotImplementedError` |
| `queue_content` | `(account_id: str, text: str, hashtags: list[str] \| None, topic: str, meta: dict \| None, scheduled_at: str \| None) -> int` | Queue row ID |
| `get_pending` | `(account_id: str) -> list[dict]` | Pending items where `scheduled_at <= now()` |
| `mark_published` | `(queue_id: int, post_id: str = "") -> None` | Sets status='published' |
| `mark_failed` | `(queue_id: int, error: str) -> None` | Sets status='failed' |

**Note:** `publish()` is a stub. Actual publishing goes through `session.browser_actions.create_post()` because Binance requires a client-side nonce + signature. The publisher manages only the queue.

---

### get_market_data (`src/content/market_data.py`)

```python
async def get_market_data(symbols: list[str]) -> dict[str, dict[str, Any]]
```

Fetches 24h ticker data from the Binance public API (`https://api.binance.com/api/v3/ticker/24hr`) for each symbol (e.g., `["BTC", "ETH"]`). Appends `USDT` to each symbol for the API call.

**Returns:**
```python
{
    "BTC": {"price": 67500.0, "change_24h": 2.3, "volume": 15000.0},
    "ETH": {"price": 3800.0, "change_24h": -1.2, "volume": 8000.0},
}
```

Fetches all symbols in parallel via `asyncio.gather()`. Failed fetches are logged and excluded from results.

---

## Business Logic

### Content Generation Pipeline (controlled by agent)
```
Agent decides to create a post for account X
  -> Agent selects topic from parser output
  -> Agent calls get_market_data(coins) for real prices
  -> Agent calls ContentGenerator.generate(style, topics, topic, market_data)
  -> Agent calls ContentPublisher.queue_content(account_id, text, ...)
  -> Agent calls ContentPublisher.get_pending(account_id)
  -> Agent calls browser_actions.create_post(ws, text, coin, sentiment)
  -> Agent calls ContentPublisher.mark_published(queue_id, post_id)
```

### Prompt Construction
System prompt includes:
- Persona style and topics
- Writing rules (conversational style, no AI cliches, $CASHTAGS, specific numbers)
- Banned phrases list (17 phrases)
- Good and bad examples
- Length guidelines: 100-280 characters for short notes, up to 1000 for analysis

User prompt includes:
- Topic name
- Up to 5 trending hashtags (with # prefix)
- Up to 5 related coins (with $ prefix)
- Current market data in format `$COIN: $price (+/-change% 24h)`

### Queue Scheduling
Items with `scheduled_at = NULL` are immediately available for publishing. Items with a future `scheduled_at` become available after the time arrives. `get_pending()` checks `scheduled_at <= utcnow()`.

---

## Edge Cases

| Situation | Expected Behavior |
|-----------|-------------------|
| AI API returns empty response | `generate()` returns empty string — agent should check and retry or skip |
| AI API rate limited or unavailable | Exception propagated to caller (agent manages retry logic) |
| `market_data` is empty dict | User prompt skips market section — AI generates without specific prices |
| Symbol not found on Binance | `_fetch_ticker` raises exception, logged as warning, symbol excluded from results |
| No pending items in queue | `get_pending()` returns empty list |
| `publish()` called | Raises `NotImplementedError` — use `browser_actions.create_post()` |
| Duplicate content in queue | No deduplication — the same text can be queued multiple times |

---

## Priority and Dependencies

- **Priority:** High
- **Depends on:** `src/bapi/client.py` (ContentPublisher holds a reference to BapiClient, though publish is a stub), `src/db/` (content_queue table)
- **Blocks:** Publishing pipeline in scheduler (content must be generated before it can be published)
