"""Binance Square SDK — unified interface for AI agent.

Agent creates SDK instance with profile serial number, calls methods.
SDK handles AdsPower connection, browser automation, and API calls internally.

Usage:
    sdk = BinanceSquareSDK(profile_serial="1")
    await sdk.connect()

    posts = await sdk.get_feed_posts(count=10)
    await sdk.comment_on_post(post_id="123", text="nice analysis")
    await sdk.like_post(post_id="123")
    await sdk.create_post(text="$BTC looking strong", coin="BTC", sentiment="bullish")

    await sdk.disconnect()
"""

import logging
from typing import Any

import httpx

from src.session.browser_actions import (
    collect_feed_posts,
    comment_on_post,
    create_post,
    create_article,
    repost,
    follow_author,
    get_user_profile,
)
from src.content.market_data import get_market_data, get_trending_coins
from src.content.news import get_crypto_news, get_article_content
from src.content.technical_analysis import get_ta_summary

logger = logging.getLogger("bsq.sdk")

ADSPOWER_BASE = "http://local.adspower.net:50325"


class BinanceSquareSDK:
    """Unified SDK for AI agent to manage Binance Square profile.

    Agent uses this as the single entry point. All browser/API details hidden.
    """

    def __init__(self, profile_serial: str):
        self._serial = profile_serial
        self._ws_endpoint: str | None = None

    # ---- Connection ----

    async def connect(self) -> None:
        """Connect to AdsPower browser profile. Must be called before any action."""
        # Check if already active
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{ADSPOWER_BASE}/api/v1/browser/active",
                params={"serial_number": self._serial},
            )
            data = resp.json()

        if data.get("code") == 0 and data.get("data", {}).get("status") == "Active":
            self._ws_endpoint = data["data"]["ws"]["puppeteer"]
            logger.info(f"Connected to active profile {self._serial}")
            return

        # Profile not active — start it
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(
                f"{ADSPOWER_BASE}/api/v1/browser/start",
                params={"user_id": "", "serial_number": self._serial, "open_tabs": "0"},
            )
            data = resp.json()

        if data.get("code") != 0:
            raise SDKError(f"Failed to start profile {self._serial}: {data.get('msg')}")

        self._ws_endpoint = data["data"]["ws"]["puppeteer"]
        logger.info(f"Started and connected to profile {self._serial}")

    async def disconnect(self) -> None:
        """Release connection. Does NOT close the browser — AdsPower manages that."""
        self._ws_endpoint = None
        logger.info(f"Disconnected from profile {self._serial}")

    @property
    def connected(self) -> bool:
        return self._ws_endpoint is not None

    def _require_connection(self) -> str:
        if not self._ws_endpoint:
            raise SDKError("Not connected. Call sdk.connect() first.")
        return self._ws_endpoint

    # ---- Data: Feed, Profiles & Trends ----

    async def get_user_profile(self, username: str) -> dict[str, Any]:
        """Fetch public profile data for a Binance Square user.

        Agent uses this to research influencers, check competitors,
        or monitor own profile growth.

        Args:
            username: Binance Square username (from profile URL)

        Returns:
            {username, name, bio, handle, following, followers, liked, shared,
             is_following, recent_posts: [{post_id, text_preview}]}
        """
        ws = self._require_connection()
        return await get_user_profile(ws, username)

    async def get_feed_posts(self, count: int = 20, tab: str = "recommended") -> list[dict[str, Any]]:
        """Get posts from feed for agent to review and decide on.

        Returns list of: {post_id, author, text, like_count}
        """
        ws = self._require_connection()
        return await collect_feed_posts(ws, count=count, tab=tab)

    async def get_trending_coins(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get top coins by market cap with 24h change from CoinGecko.

        No browser needed. No API key required.

        Args:
            limit: Number of coins to return. Default: 10

        Returns:
            [{rank, symbol, name, price, change_24h, market_cap, volume_24h}]
        """
        return await get_trending_coins(limit)

    async def get_crypto_news(self, limit: int = 10) -> list[dict[str, Any]]:
        """Fetch latest crypto news headlines from RSS feeds.

        No browser needed. Sources: CoinDesk, CoinTelegraph, Decrypt.

        Args:
            limit: Number of articles to return. Default: 10

        Returns:
            [{title, source, url, published_at}] sorted newest first
        """
        return await get_crypto_news(limit)

    async def get_article_content(self, url: str) -> dict[str, Any]:
        """Fetch full text of a news article.

        Call this when a headline from get_crypto_news() is interesting
        enough to write a deep post or article about.

        Args:
            url: Article URL from get_crypto_news()

        Returns:
            {title, text, url, published_at}
        """
        return await get_article_content(url)

    async def get_ta_summary(self, symbol: str = "BTC", timeframe: str = "1D") -> dict[str, Any]:
        """Compute technical analysis summary for a trading pair.

        Fetches 200 candles from Binance and computes key indicators.
        Agent uses this as a basis for forming its own market view.

        Args:
            symbol: Coin symbol, e.g. "BTC", "ETH", "SOL"
            timeframe: "1H", "4H", "1D" (default), "1W"

        Returns:
            {symbol, timeframe, price, change_pct, trend, signal,
             rsi, rsi_zone, macd, macd_signal, macd_cross,
             ma20, ma50, ma200, price_vs_ma200, support, resistance}
        """
        return await get_ta_summary(symbol, timeframe)

    async def get_market_data(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        """Get current price, 24h change, volume for coins.

        Args:
            symbols: e.g. ["BTC", "ETH", "SOL"]

        Returns:
            {symbol: {price, change_24h, volume}}
        """
        return await get_market_data(symbols)

    # ---- Actions ----

    async def comment_on_post(self, post_id: str, text: str) -> dict[str, Any]:
        """Post a comment on a specific post.

        Handles Follow & Reply popup if author restricts comments.

        Returns:
            {success, post_id, followed}
        """
        ws = self._require_connection()
        return await comment_on_post(ws, post_id, text)

    async def create_post(
        self,
        text: str,
        coin: str | None = None,
        sentiment: str | None = None,
        image_path: str | None = None,
    ) -> dict[str, Any]:
        """Create a new post on Binance Square.

        Args:
            text: Post text (use $BTC style for coins, include #hashtags)
            coin: Optional coin ticker to attach chart (e.g. "BTC")
            sentiment: Optional "bullish" or "bearish"
            image_path: Optional local file path for image

        Returns:
            {success, post_id, response}
        """
        ws = self._require_connection()
        return await create_post(ws, text, coin=coin, sentiment=sentiment, image_path=image_path)

    async def create_article(
        self,
        title: str,
        body: str,
        cover_path: str | None = None,
    ) -> dict[str, Any]:
        """Create a long-form article on Binance Square.

        Returns:
            {success, post_id, response}
        """
        ws = self._require_connection()
        return await create_article(ws, title, body, cover_path=cover_path)

    async def quote_repost(self, post_id: str, comment: str = "") -> dict[str, Any]:
        """Quote-repost a post with optional comment.

        Returns:
            {success, original_post_id}
        """
        ws = self._require_connection()
        return await repost(ws, post_id, comment=comment)

    async def follow_user(self, post_id: str) -> dict[str, Any]:
        """Follow the author of a post. Skips if already following.

        Returns:
            {success, post_id, action: "followed"|"already_following"|"skipped"}
        """
        ws = self._require_connection()
        return await follow_author(ws, post_id)

    async def like_post(self, post_id: str) -> dict[str, Any]:
        """Like a post via browser click.

        Returns:
            {success, post_id}
        """
        ws = self._require_connection()
        # Like via browser — navigate to post and click like button
        from src.session.browser_actions import _get_page
        from src.session import page_map
        import asyncio

        pw, browser, page = await _get_page(ws)
        try:
            post_url = page_map.POST_URL_TEMPLATE.format(post_id=post_id)
            await page.goto(post_url, wait_until="domcontentloaded", timeout=60_000)
            await asyncio.sleep(4)
            like_btn = page.locator(page_map.POST_LIKE_BUTTON).first
            await like_btn.click()
            await asyncio.sleep(2)
            logger.info(f"Liked post {post_id}")
            return {"success": True, "post_id": post_id}
        except Exception as e:
            logger.error(f"Like failed on {post_id}: {e}")
            return {"success": False, "error": str(e)}
        finally:
            await pw.stop()


    async def download_image(self, image_url: str, filename: str | None = None) -> str:
        """Download an image from URL and save locally.

        Args:
            image_url: Direct URL to image file
            filename: Optional filename, auto-generated if not provided

        Returns:
            Absolute path to saved image
        """
        import os
        import time

        images_dir = os.path.join("data", "images")
        os.makedirs(images_dir, exist_ok=True)

        if not filename:
            ext = image_url.rsplit(".", 1)[-1].split("?")[0]
            if ext not in ("png", "jpg", "jpeg", "gif", "webp"):
                ext = "jpg"
            filename = f"{int(time.time())}.{ext}"

        filepath = os.path.abspath(os.path.join(images_dir, filename))

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(image_url)
            resp.raise_for_status()
            with open(filepath, "wb") as f:
                f.write(resp.content)

        logger.info(f"Image downloaded: {filepath} ({len(resp.content)} bytes)")
        return filepath

    async def take_screenshot(
        self,
        url: str,
        selector: str | None = None,
        crop: dict[str, int] | None = None,
        wait: int = 5,
    ) -> str:
        """Take a screenshot of a page or element via browser.

        Uses AdsPower profile browser so IP/fingerprint matches the account.

        Args:
            url: Page URL to navigate to
            selector: Optional CSS selector to screenshot specific element
            crop: Optional {x, y, width, height} to crop the screenshot
            wait: Seconds to wait after page load (default 5)

        Returns:
            Absolute path to saved screenshot file (data/screenshots/<timestamp>.png)
        """
        import asyncio
        import os
        import time
        from src.session.browser_actions import _get_page

        ws = self._require_connection()
        pw, browser, page = await _get_page(ws)

        screenshots_dir = os.path.join("data", "screenshots")
        os.makedirs(screenshots_dir, exist_ok=True)
        filename = f"{int(time.time())}.png"
        filepath = os.path.abspath(os.path.join(screenshots_dir, filename))

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            await asyncio.sleep(wait)

            # Dismiss cookie banners
            try:
                await page.locator("button#onetrust-reject-all-handler").click(timeout=3_000)
                await asyncio.sleep(1)
            except Exception:
                pass

            if selector:
                element = page.locator(selector).first
                await element.screenshot(path=filepath)
            elif crop:
                await page.screenshot(path=filepath, clip=crop)
            else:
                await page.screenshot(path=filepath)

            logger.info(f"Screenshot saved: {filepath}")
            return filepath

        except Exception as e:
            logger.error(f"take_screenshot: {e}, url={url}")
            raise SDKError(f"Screenshot failed: {e}") from e
        finally:
            await pw.stop()


    async def screenshot_chart(self, symbol: str = "BTC_USDT", timeframe: str = "1D") -> str:
        """Screenshot the Binance spot chart for a trading pair.

        Captures the kline chart element and pads it to 16:9 horizontal
        ratio suitable for article covers and post images.
        Adapts to any window size — no hardcoded coordinates.

        Args:
            symbol: Trading pair (e.g. "BTC_USDT", "ETH_USDT", "SOL_USDT")
            timeframe: Chart timeframe — "1D" (default), "4H", "1H", "1W"

        Returns:
            Absolute path to saved screenshot
        """
        import asyncio
        import os
        import time
        from src.session.browser_actions import _get_page

        ws = self._require_connection()
        pw, browser, page = await _get_page(ws)

        screenshots_dir = os.path.join("data", "screenshots")
        os.makedirs(screenshots_dir, exist_ok=True)
        filename = f"{symbol.replace('_', '')}_{timeframe}_{int(time.time())}.png"
        filepath = os.path.abspath(os.path.join(screenshots_dir, filename))

        try:
            url = f"https://www.binance.com/en/trade/{symbol}"
            await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            await asyncio.sleep(8)

            # Dismiss cookie banner
            try:
                await page.locator("button#onetrust-reject-all-handler").click(timeout=3_000)
                await asyncio.sleep(1)
            except Exception:
                pass

            # Select timeframe if not default
            if timeframe != "1D":
                try:
                    tf_btn = page.locator(f"text='{timeframe}'").first
                    await tf_btn.click(timeout=3_000)
                    await asyncio.sleep(3)
                except Exception:
                    pass

            # Screenshot the chart element directly — adapts to any window size
            chart = page.locator(".kline-container").first
            await chart.screenshot(path=filepath)

            # Pad to 16:9 if needed
            from PIL import Image
            img = Image.open(filepath)
            w, h = img.size
            target_h = int(w * 9 / 16)
            if h < target_h:
                # Pad bottom with dark background
                padded = Image.new("RGB", (w, target_h), color=(17, 17, 24))
                padded.paste(img, (0, 0))
                padded.save(filepath)

            logger.info(f"Chart screenshot saved: {filepath}")
            return filepath

        except Exception as e:
            logger.error(f"screenshot_chart: {e}, symbol={symbol}")
            raise SDKError(f"Chart screenshot failed: {e}") from e
        finally:
            await pw.stop()


class SDKError(Exception):
    """Raised when SDK operation fails."""
    pass
