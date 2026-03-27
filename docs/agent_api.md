# Binance Square SDK — Agent API Reference

SDK for AI agent to manage a Binance Square profile. Agent decides, SDK executes.

## Quick Start

```python
from src.sdk import BinanceSquareSDK

sdk = BinanceSquareSDK(profile_serial="1")
await sdk.connect()

# Read feed
posts = await sdk.get_feed_posts(count=10)

# Comment on a post
await sdk.comment_on_post(post_id="123456", text="interesting take on btc support levels")

# Create a post
await sdk.create_post(
    text="$BTC holding 68k despite macro chaos. $ETH down harder at -4%\n\n#Bitcoin #CryptoMarket",
    coin="BTC",
    sentiment="bearish",
)

await sdk.disconnect()
```

## Connection

### `sdk.connect()`
Connect to AdsPower browser profile. Must be called before any action.
- Checks if profile is already active, connects to it
- If not active, starts the browser via AdsPower API
- Raises `SDKError` if connection fails

### `sdk.disconnect()`
Release connection. Does NOT close the browser.

### `sdk.connected` (property)
Returns `True` if connected.

---

## Data Methods

### `sdk.get_feed_posts(count=20, tab="recommended")`
Collect posts from Binance Square feed for agent to review.

**Parameters:**
- `count` (int): Target number of posts to collect. Default: 20
- `tab` (str): `"recommended"` or `"following"`. Default: `"recommended"`

**Returns:** `list[dict]` — each dict:
```python
{
    "post_id": "305668937425010",
    "author": "CryptoAnalyst",
    "text": "Full post text without cookie banners...",
    "like_count": 244
}
```

**Notes:**
- Navigates to feed in browser, scrolls to load posts, visits each to extract text
- Filters out posts with text < 30 chars
- Takes ~2-3 min for 8-10 posts (browser navigation per post)

### `sdk.get_market_data(symbols)`
Get current prices from Binance public API. No browser needed.

**Parameters:**
- `symbols` (list[str]): Coin tickers, e.g. `["BTC", "ETH", "SOL"]`

**Returns:** `dict[str, dict]`
```python
{
    "BTC": {"price": 69111.41, "change_24h": -2.65, "volume": 28453.7},
    "ETH": {"price": 2072.10, "change_24h": -4.22, "volume": 193847.2}
}
```

### `sdk.get_user_profile(username)`
Fetch public profile data for any Binance Square user.

**Parameters:**
- `username` (str): Username from profile URL

**Returns:** `dict`
```python
{
    "username": "CZ", "name": "CZ", "handle": "@Binance co-founder...",
    "bio": "...", "following": "27", "followers": "1.8M+",
    "liked": "301.6K+", "shared": "12.9K+", "is_following": False,
    "recent_posts": [{"post_id": "305942...", "text_preview": "Not owned..."}]
}
```

### `sdk.get_post_stats(post_id)`
Fetch engagement stats for a specific post.

**Parameters:**
- `post_id` (str): Post ID

**Returns:** `dict`
```python
{"post_id": "306032...", "likes": "1", "comments": "0", "quotes": "0",
 "title_preview": "me watching my portfolio..."}
```

### `sdk.get_my_stats()`
Fetch own profile stats from Creator Center. No parameters — uses connected profile.

**Returns:** `dict`
```python
{
    "username": "aisama", "handle": "@aisama", "name": "aisama",
    "followers": "3", "following": "10", "liked": "26", "shared": "0",
    "dashboard": {
        "period": "Period: 2026-03-26...",
        "published": "3", "followers_gained": "0",
        "views": "106", "likes": "2", "shares": "0"
    }
}
```

### `sdk.get_trending_coins(limit=10)`
Get top coins by market cap with 24h stats from CoinGecko. No browser, no API key.

**Parameters:**
- `limit` (int): Number of coins. Default: 10

**Returns:** `list[dict]`
```python
[
    {"rank": 1, "symbol": "BTC", "name": "Bitcoin", "price": 69111.41,
     "change_24h": -2.65, "market_cap": 1360000000000, "volume_24h": 28000000000},
    ...
]
```

### `sdk.get_crypto_news(limit=10)`
Fetch latest crypto news headlines from RSS feeds. No browser, no API key.

Sources: CoinDesk, CoinTelegraph, Decrypt.

**Parameters:**
- `limit` (int): Total articles to return. Default: 10

**Returns:** `list[dict]` sorted by date (newest first)
```python
[
    {"title": "Bitcoin Surges Past $70K...", "source": "CoinDesk",
     "url": "https://coindesk.com/...", "published_at": "2026-03-27T14:30:00+00:00"},
    ...
]
```

### `sdk.get_article_content(url)`
Fetch full text of a news article. Call when a headline from `get_crypto_news()` is worth a deep post.

**Parameters:**
- `url` (str): Article URL from `get_crypto_news()`

**Returns:** `dict`
```python
{"title": "Bitcoin Surges...", "text": "Full article text...", "url": "...", "published_at": "2026-03-27"}
```

### `sdk.get_ta_summary(symbol="BTC", timeframe="1D")`
Technical analysis summary. Fetches 200 candles from Binance, computes RSI, MACD, MAs, support/resistance.

Agent uses this as a basis for forming its own market view — not as mechanical signals.

**Parameters:**
- `symbol` (str): Coin symbol, e.g. `"BTC"`, `"ETH"`, `"SOL"`
- `timeframe` (str): `"1H"`, `"4H"`, `"1D"` (default), `"1W"`

**Returns:** `dict`
```python
{
    "symbol": "BTC", "timeframe": "1D",
    "price": 69111.41, "change_pct": -2.65,
    "trend": "bullish",           # bullish | bearish | neutral
    "signal": "neutral",          # buy | sell | neutral
    "rsi": 54.32, "rsi_zone": "neutral",  # oversold | neutral | overbought
    "macd": 245.12, "macd_signal": 198.45, "macd_cross": "none",
    "ma20": 68500.0, "ma50": 67200.0, "ma200": 62100.0,
    "price_vs_ma200": "above",
    "support": 66800.0, "resistance": 71200.0,
}
```

---

## Action Methods

### `sdk.comment_on_post(post_id, text)`
Post a comment on a specific post.

**Parameters:**
- `post_id` (str): Post ID from feed or URL
- `text` (str): Comment text (1-3 sentences, conversational)

**Returns:** `dict`
```python
{"success": True, "post_id": "123", "followed": False}
# followed=True means "Follow & Reply" popup was triggered (auto-followed author)
```

**Notes:**
- Navigates to post, scrolls to reply input, types text, clicks Reply
- Handles "Follow & Reply" popup automatically
- ~30-50 sec per comment

### `sdk.create_post(text, coin=None, sentiment=None, image_path=None)`
Create a new post on Binance Square.

**Parameters:**
- `text` (str): Post text. Use `$BTC` style for coin mentions. Include `#hashtags`
- `coin` (str, optional): Coin ticker to attach chart (e.g. `"BTC"`)
- `sentiment` (str, optional): `"bullish"` or `"bearish"` — sets price expectation mark
- `image_path` (str, optional): Local file path to attach image

**Returns:** `dict`
```python
{"success": True, "post_id": "305847920721665", "response": {...}}
```

**Notes:**
- Uses inline compose editor on Square main page
- Chart attachment: searches coin and selects from popup
- After each #hashtag, auto-presses Escape to dismiss autocomplete dropdown
- ~60-90 sec per post

### `sdk.create_article(title, body, cover_path=None)`
Create a long-form article.

**Parameters:**
- `title` (str): Article title
- `body` (str): Full article body with `$CASHTAGS` and `#hashtags`
- `cover_path` (str, optional): Local file path for cover image

**Returns:** `dict` — same format as `create_post`

### `sdk.quote_repost(post_id, comment="")`
Quote-repost a post with optional comment.

**Parameters:**
- `post_id` (str): Post to repost
- `comment` (str): Your take on the original post

**Returns:** `dict`
```python
{"success": True, "original_post_id": "123"}
```

### `sdk.follow_user(post_id)`
Follow the author of a post. Skips if already following.

**Parameters:**
- `post_id` (str): Post ID — will navigate to it and find Follow button

**Returns:** `dict`
```python
{"success": True, "post_id": "123", "action": "followed"}
# action: "followed" | "already_following" | "skipped"
```

### `sdk.like_post(post_id)`
Like a post via browser click.

**Parameters:**
- `post_id` (str): Post to like

**Returns:** `dict`
```python
{"success": True, "post_id": "123"}
```

---

## Media Methods

### `sdk.download_image(image_url, filename=None)`
Download an image from URL and save locally.

**Parameters:**
- `image_url` (str): Direct URL to image file
- `filename` (str, optional): Filename to save as. Auto-generated from timestamp if not provided

**Returns:** `str` — absolute path to saved file

```python
path = await sdk.download_image("https://example.com/meme.jpg")
# Returns: "C:/...absolute.../data/images/1711234567.jpg"

# Then use in post:
await sdk.create_post(text="...", image_path=path)
```

**Notes:**
- Saved to `data/images/`
- Supports: png, jpg, jpeg, gif, webp
- Does NOT use browser — direct httpx download

---

### `sdk.take_screenshot(url, selector=None, crop=None, wait=5)`
Take a screenshot of any page via AdsPower browser.

Uses the profile browser so IP/fingerprint matches the account.

**Parameters:**
- `url` (str): Page URL to navigate to
- `selector` (str, optional): CSS selector to screenshot specific element only
- `crop` (dict, optional): `{x, y, width, height}` to crop the screenshot
- `wait` (int): Seconds to wait after page load. Default: 5

**Returns:** `str` — absolute path to saved file (`data/screenshots/<timestamp>.png`)

```python
# Full page screenshot
path = await sdk.take_screenshot("https://coindesk.com/markets/")

# Specific element
path = await sdk.take_screenshot(
    url="https://example.com",
    selector=".chart-container",
)
```

**Notes:**
- Raises `SDKError` if screenshot fails
- Dismisses cookie banners automatically

---

### `sdk.screenshot_chart(symbol="BTC_USDT", timeframe="1D")`
Screenshot Binance spot chart for a trading pair. Ready for post/article covers.

Captures `.kline-container` element and pads to 16:9 horizontal ratio.

**Parameters:**
- `symbol` (str): Trading pair. Default: `"BTC_USDT"`. Examples: `"ETH_USDT"`, `"SOL_USDT"`
- `timeframe` (str): `"1D"` (default), `"4H"`, `"1H"`, `"1W"`

**Returns:** `str` — absolute path to saved file (`data/screenshots/<SYMBOL><TF>_<timestamp>.png`)

```python
# BTC daily chart for article cover
cover = await sdk.screenshot_chart("BTC_USDT", "1D")
await sdk.create_article(title="BTC Analysis", body="...", cover_path=cover)

# ETH 4H chart for post
chart = await sdk.screenshot_chart("ETH_USDT", "4H")
await sdk.create_post(text="$ETH 4H setup...", image_path=chart)
```

**Notes:**
- Background color: `#111118` (matches Binance dark theme)
- Raises `SDKError` if chart element not found

---

## Content Rules

All content must follow rules from `config/content_rules.yaml`:

- **Language:** English only
- **Style:** Casual, conversational, like a real person. No AI clichés
- **Coins:** Always use `$BTC` not "Bitcoin", `$ETH` not "Ethereum"
- **Posts:** Min 2 paragraphs, include `$CASHTAGS` and `#hashtags`, use real market data only
- **Comments:** 1-3 sentences max, talk TO the author, react to specific content
- **Quote reposts:** Add your own take, `$CASHTAGS` only if original post is about a specific coin
- **Banned phrases:** "let's dive into", "game-changer", "unprecedented", "comprehensive guide", etc.

## Error Handling

All methods return `dict` with `success` field:
```python
{"success": True, ...}   # action completed
{"success": False, "error": "description"}  # action failed
```

`SDKError` is raised for connection issues (not connected, AdsPower unavailable).

## Human-like Behavior

When performing multiple actions, add delays between them:
- Between comments: 20-40 seconds
- Between different action types: 15-30 seconds
- The SDK does NOT add delays automatically — agent must manage timing
