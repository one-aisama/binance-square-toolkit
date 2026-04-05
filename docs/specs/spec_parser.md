# Specification: Parser Module

**Path:** `src/parser/`
**Files:** `fetcher.py`, `aggregator.py`, `models.py`

---

## Description

The Parser module fetches raw content from Binance Square (posts and articles via bapi, fear/greed index, hot hashtags), normalizes it into typed dataclasses, and ranks trending topics by engagement score. Its output is the primary information source for the content generation pipeline: it shows the agent what the community is talking about and which topics are gaining the most traction.

---

## User Stories

- As an agent, I want to get all fresh feed posts and articles in a single call, so I have a unified content list for analysis.
- As an agent, I want posts to be deduplicated by post_id, so I don't process the same content twice.
- As an agent, I want trending hashtags ranked by engagement score, so I can pick the topic with the strongest signal for content generation.
- As an agent, I want the fear/greed index and popular coins loaded alongside posts, so I can account for market sentiment when creating content.
- As an agent, I want raw bapi data normalized into typed dataclasses, so downstream code doesn't parse raw dicts.

---

## Data Model

### ParsedPost (`src/parser/models.py`)

```python
@dataclass
class ParsedPost:
    post_id: str
    author_name: str = ""
    author_id: str = ""
    card_type: str = ""
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    hashtags: list[str] = field(default_factory=list)
    trading_pairs: list[str] = field(default_factory=list)
    is_ai_created: bool = False
    created_at: int = 0   # Unix timestamp milliseconds
    text_preview: str = ""  # Truncated to 200 chars
```

### Topic (`src/parser/models.py`)

```python
@dataclass
class Topic:
    name: str
    hashtags: list[str] = field(default_factory=list)
    coins: list[str] = field(default_factory=list)
    engagement_score: float = 0.0
    post_count: int = 0
```

### DB Tables (written by the scheduler/orchestrator, not the module itself)

```sql
CREATE TABLE IF NOT EXISTS parsed_posts (
    id INTEGER PRIMARY KEY,
    cycle_id TEXT NOT NULL,
    post_id TEXT NOT NULL,
    author_name TEXT,
    card_type TEXT,
    view_count INTEGER,
    like_count INTEGER,
    comment_count INTEGER,
    share_count INTEGER,
    hashtags TEXT,         -- JSON array
    trading_pairs TEXT,    -- JSON array
    is_ai_created BOOLEAN,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(cycle_id, post_id)
);

CREATE TABLE IF NOT EXISTS parsed_trends (
    id INTEGER PRIMARY KEY,
    cycle_id TEXT NOT NULL,
    topics TEXT NOT NULL,          -- JSON array of Topic objects
    fear_greed_index INTEGER,
    popular_coins TEXT,            -- JSON array
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

The parser module returns Python objects; persistence is the caller's responsibility.

---

## API

### TrendFetcher (`src/parser/fetcher.py`)

```python
class TrendFetcher:
    def __init__(self, client: BapiClient)
```

| Method | Signature | Returns |
|--------|-----------|---------|
| `fetch_all` | `(article_pages: int = 5, feed_pages: int = 5) -> list[ParsedPost]` | Deduplicated list of ParsedPost |
| `fetch_fear_greed` | `() -> dict` | Raw dict from `BapiClient.get_fear_greed()` |
| `fetch_hot_hashtags` | `() -> list[dict]` | Raw list from `BapiClient.get_hot_hashtags()` |
| `_fetch_articles` | `(pages: int = 5) -> list[ParsedPost]` | Private -- fetches top articles across N pages |
| `_fetch_feed` | `(pages: int = 5) -> list[ParsedPost]` | Private -- fetches recommended feed across N pages |

`fetch_all` calls `_fetch_articles` and `_fetch_feed`, merges results, deduplicates by `post_id` (articles first, feed second -- on collision articles take priority), and returns the combined list.

---

### _extract_post (`src/parser/fetcher.py`)

```python
def _extract_post(raw: dict[str, Any]) -> ParsedPost | None
```

Module-level function. Normalizes a raw bapi post dict into `ParsedPost`. Returns `None` if `post_id` cannot be extracted.

Field resolution paths (tries multiple keys since bapi response structure differs between feed and articles):

| ParsedPost Field | Lookup Order |
|------------------|--------------|
| `post_id` | `contentDetail.id` -> `contentDetail.contentId` |
| `author_name` | `contentDetail.authorName` -> `contentDetail.nickname` |
| `author_id` | `contentDetail.authorId` -> `contentDetail.userId` |
| `card_type` | `contentDetail.cardType` -> `contentDetail.type` |
| `text_preview` | `contentDetail.title` -> `contentDetail.text` (truncated to 200) |
| `hashtags` | `contentDetail.hashtagList[].name` or `hashtagName` or raw str |
| `trading_pairs` | `contentDetail.tradingPairs[].symbol` or `name`; or `contentDetail.cashtagList` |

If the raw dict has no `contentDetail` wrapper, the dict itself is used.

---

### rank_topics / compute_engagement (`src/parser/aggregator.py`)

```python
def compute_engagement(post: ParsedPost) -> float
```
Formula: `view_count * 0.3 + like_count * 0.5 + comment_count * 0.2`

```python
def rank_topics(posts: list[ParsedPost], top_n: int = 10) -> list[Topic]
```

Groups posts by hashtag (normalized: lowercase, `#` stripped). Accumulates `engagement_score` and `post_count` for each hashtag. Collects `trading_pairs` for each hashtag into a `set`. Sorts by total engagement descending. Returns the top `top_n` Topics.

Posts without hashtags are grouped under `"_untagged"` internally and excluded from the returned list.

---

## Business Logic

### Pagination
`_fetch_articles` and `_fetch_feed` iterate pages from 1 to N inclusive. An error on a page (any exception from BapiClient) is logged as a warning, iteration continues -- partial data is returned instead of a full abort.

### Deduplication
In `fetch_all`: after concatenating articles + feed posts, a `seen: set[str]` is used on `post_id` values. First occurrence wins. Since articles come first in the concatenation, they take priority over feed duplicates.

### Engagement Score Weights
```
view_count   x 0.3  (reach)
like_count   x 0.5  (direct engagement -- highest weight)
comment_count x 0.2  (discussion quality)
```
`share_count` is not included in the formula (present in the model but not used in scoring).

### Coin Collection per Topic
Each coin from `post.trading_pairs` is added to a `set` for each hashtag of that post. The final `Topic.coins` is `sorted(set)` for deterministic output.

### Hashtag Normalization
`tag.lower().strip("#")` -- strips the leading `#` and lowercases. Empty tags after cleanup are skipped.

---

## Edge Cases

| Scenario | Expected Behavior |
|----------|-------------------|
| BapiClient returns an empty list for a page | Page skipped silently, next page is tried |
| `_extract_post` cannot find post_id | Returns `None`, post is silently discarded |
| All pages failed (network unavailable) | `fetch_all` returns an empty list `[]` |
| Post without hashtags | Counted under `"_untagged"` internally, excluded from `rank_topics` output |
| `rank_topics([])` | Immediately returns `[]` |
| Two posts with the same post_id | First occurrence is kept (articles before feed) |
| `top_n` is larger than the number of unique hashtags | All available topics are returned (fewer than `top_n`) |
| `text_preview` source is too long | Truncated to 200 characters via `[:200]` slice |

---

## Priority and Dependencies

- **Priority:** High
- **Depends on:** `src/bapi/client.py` (BapiClient must be created with valid credentials before parsing)
- **Blocks:** `src/content/generator.py` (needs Topic + market_data for post generation), `src/activity/target_selector.py` (needs ParsedPost list for target selection)
