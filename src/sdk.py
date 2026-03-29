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

import asyncio
import logging
from typing import Any

import httpx

from src.runtime.guard import ActionGuard, Verdict

from src.session.browser_actions import (
    collect_feed_posts,
    comment_on_post,
    create_post,
    create_article,
    engage_post,
    repost,
    follow_author,
    get_user_profile,
    get_post_comments,
    get_my_comment_replies,
    get_post_stats,
    get_my_stats,
)
from src.content.market_data import get_market_data, get_trending_coins
from src.content.news import get_crypto_news, get_article_content
from src.content.technical_analysis import get_ta_summary
from src.content.validator import validate_post, validate_comment, validate_article, validate_quote, verify_prices
from src.runtime.behavior import warm_up, mouse_move_to

logger = logging.getLogger("bsq.sdk")

ADSPOWER_BASE = "http://local.adspower.net:50325"


class BinanceSquareSDK:
    """Unified SDK for AI agent to manage Binance Square profile.

    Agent uses this as the single entry point. All browser/API details hidden.
    """

    def __init__(self, profile_serial: str = "1", account_id: str = "default", db_path: str = "data/bsq.db"):
        self._serial = profile_serial
        self._account_id = account_id
        self._db_path = db_path
        self._ws_endpoint: str | None = None
        self._guard: ActionGuard | None = None
        self._pw = None
        self._browser = None
        self._page = None

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
            await self._init_persistent_page()
            self._init_guard()
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

        # Create persistent Playwright page
        await self._init_persistent_page()
        self._init_guard()

    def _init_guard(self) -> None:
        """Create guard with limits from account config. Always called on connect."""
        from src.accounts.limiter import ActionLimiter
        from src.accounts.manager import LimitsConfig
        limiter = ActionLimiter(db_path=self._db_path)
        limits = LimitsConfig()  # defaults, can be loaded from account yaml later
        self._guard = ActionGuard(
            limiter=limiter,
            limits=limits,
            account_id=self._account_id,
        )
        logger.info(f"Guard initialized for {self._account_id}")

    async def _init_persistent_page(self) -> None:
        """Create persistent Playwright connection. One page for entire session."""
        from playwright.async_api import async_playwright
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.connect_over_cdp(self._ws_endpoint)
        context = self._browser.contexts[0] if self._browser.contexts else await self._browser.new_context()
        self._page = context.pages[0] if context.pages else await context.new_page()
        logger.info("Persistent page created")

    async def disconnect(self) -> None:
        """Release connection and close persistent page."""
        if self._pw:
            await self._pw.stop()
            self._pw = None
            self._browser = None
            self._page = None
        self._ws_endpoint = None
        logger.info(f"Disconnected from profile {self._serial}")

    @property
    def connected(self) -> bool:
        return self._ws_endpoint is not None

    def can_finish(self) -> tuple[bool, str]:
        """Check if session minimum is met. Agent calls this before ending session."""
        if self._guard:
            return self._guard.can_finish()
        return True, "No guard"

    def get_minimum_status(self) -> dict:
        """Get progress toward session minimum."""
        if self._guard:
            return self._guard.get_minimum_status()
        return {}

    def _require_connection(self) -> str:
        if not self._ws_endpoint:
            raise SDKError("Not connected. Call sdk.connect() first.")
        return self._ws_endpoint

    async def _check_guard(self, action_type: str) -> tuple[bool, str]:
        """Check guard before action. Returns (allowed, reason).

        Guard is always present (created on connect).
        """
        if not self._guard:
            return True, ""

        decision = await self._guard.check(action_type)
        if decision.verdict == Verdict.ALLOW:
            return True, ""
        elif decision.verdict == Verdict.WAIT:
            await asyncio.sleep(decision.wait_seconds)
            decision = await self._guard.check(action_type)
            if decision.verdict == Verdict.ALLOW:
                return True, ""
            return False, decision.reason
        elif decision.verdict == Verdict.DENIED:
            logger.warning(f"Guard denied {action_type}: {decision.reason}")
            return False, decision.reason
        elif decision.verdict == Verdict.SESSION_OVER:
            logger.error(f"Guard: session over — {decision.reason}")
            return False, decision.reason
        return False, "Unknown guard verdict"

    def _record_guard(self, action_type: str, success: bool, error: str | None = None):
        """Record action result in guard if guard is set."""
        if self._guard:
            self._guard.record(action_type, success, error)

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
        return await get_user_profile(ws, username, page=self._page)

    async def get_post_stats(self, post_id: str) -> dict[str, Any]:
        """Fetch engagement stats for a specific post.

        Agent uses this to check how own posts performed.

        Args:
            post_id: Post ID

        Returns:
            {post_id, likes, comments, quotes, title_preview}
        """
        ws = self._require_connection()
        return await get_post_stats(ws, post_id, page=self._page)

    async def get_post_comments(self, post_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Fetch comments on a specific post.

        Agent uses this to check if someone commented on own posts
        and reply to build community.

        Args:
            post_id: Post ID
            limit: Max comments to return (default 20)

        Returns:
            [{author, text}]
        """
        ws = self._require_connection()
        return await get_post_comments(ws, post_id, limit=limit, page=self._page)

    async def get_my_comment_replies(self, username: str = "aisama") -> list[dict[str, Any]]:
        """Find replies to agent's comments on other people's posts.

        Goes to profile → Replies tab, finds comments that received replies,
        clicks into each to read who replied and what they said.

        Agent uses this as PRIORITY #1 every session — reply to people
        who engaged with your comments.

        Args:
            username: Agent's Binance Square username

        Returns:
            [{comment_text, comment_post_id, reply_count,
              replies: [{author, author_handle, text}]}]
        """
        ws = self._require_connection()
        return await get_my_comment_replies(ws, username=username, page=self._page)

    async def get_my_stats(self) -> dict[str, Any]:
        """Fetch own profile stats from Creator Center.

        Agent uses this to monitor growth and adapt strategy.

        Returns:
            {username, handle, name, bio, followers, following, liked, shared,
             dashboard: {period, published, followers_gained, views, likes, comments, shares, quotes}}
        """
        ws = self._require_connection()
        return await get_my_stats(ws, page=self._page)

    async def get_feed_posts(self, count: int = 20, tab: str = "recommended") -> list[dict[str, Any]]:
        """Get posts from feed for agent to review and decide on.

        Returns list of: {post_id, author, text, like_count}
        """
        ws = self._require_connection()
        return await collect_feed_posts(ws, count=count, tab=tab, page=self._page)

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

    async def comment_on_post(
        self, post_id: str, text: str, skip_validation: bool = False,
    ) -> dict[str, Any]:
        """Post a comment on a specific post.

        Validates comment text before posting. Handles Follow & Reply popup.

        Returns:
            {success, post_id, followed} or {success: False, validation_errors}
        """
        allowed, reason = await self._check_guard("comment")
        if not allowed:
            return {"success": False, "error": f"Guard denied: comment — {reason}"}

        if not skip_validation:
            result = validate_comment(text)
            if not result.valid:
                logger.warning(f"comment_on_post: validation failed — {result.errors}")
                return {
                    "success": False,
                    "validation_errors": result.errors,
                    "validation_warnings": result.warnings,
                }
            if result.warnings:
                logger.info(f"comment_on_post: validation warnings — {result.warnings}")

        ws = self._require_connection()
        try:
            response = await comment_on_post(ws, post_id, text, page=self._page)
            self._record_guard("comment", success=response.get("success", False))
            return response
        except Exception as e:
            self._record_guard("comment", success=False, error=str(e))
            raise

    async def create_post(
        self,
        text: str,
        coin: str | None = None,
        sentiment: str | None = None,
        image_path: str | None = None,
        recent_posts: list[str] | None = None,
        skip_validation: bool = False,
    ) -> dict[str, Any]:
        """Create a new post on Binance Square.

        Validates content before publishing. Pass skip_validation=True to bypass.

        Args:
            text: Post text (use $BTC style for coins, include #hashtags)
            coin: Optional coin ticker to attach chart (e.g. "BTC")
            sentiment: Optional "bullish" or "bearish"
            image_path: Optional local file path for image
            recent_posts: Optional list of recent post texts for duplicate check
            skip_validation: Skip content validation (default False)

        Returns:
            {success, post_id, response} or {success: False, validation_errors, validation_warnings}
        """
        allowed, reason = await self._check_guard("post")
        if not allowed:
            return {"success": False, "error": f"Guard denied: post — {reason}"}

        if not skip_validation:
            result = validate_post(text, recent_posts=recent_posts)
            if not result.valid:
                logger.warning(f"create_post: validation failed — {result.errors}")
                return {
                    "success": False,
                    "validation_errors": result.errors,
                    "validation_warnings": result.warnings,
                }
            if result.warnings:
                logger.info(f"create_post: validation warnings — {result.warnings}")

            # Verify prices in text against live market data
            try:
                market = await get_market_data(["BTC", "ETH", "SOL", "BNB"])
                price_warnings = verify_prices(text, market)
                if price_warnings:
                    logger.warning(f"create_post: price verification warnings — {price_warnings}")
                    return {
                        "success": False,
                        "validation_errors": price_warnings,
                        "validation_warnings": [],
                    }
            except Exception as e:
                logger.warning(f"create_post: price verification skipped — {e}")

        ws = self._require_connection()
        try:
            response = await create_post(ws, text, coin=coin, sentiment=sentiment, image_path=image_path, page=self._page)
            self._record_guard("post", success=response.get("success", False))
            return response
        except Exception as e:
            self._record_guard("post", success=False, error=str(e))
            raise

    async def create_article(
        self,
        title: str,
        body: str,
        cover_path: str | None = None,
        skip_validation: bool = False,
    ) -> dict[str, Any]:
        """Create a long-form article on Binance Square.

        Validates content before publishing. Pass skip_validation=True to bypass.

        Returns:
            {success, post_id, response} or {success: False, validation_errors, validation_warnings}
        """
        allowed, reason = await self._check_guard("post")
        if not allowed:
            return {"success": False, "error": f"Guard denied: post — {reason}"}

        if not skip_validation:
            result = validate_article(title, body)
            if not result.valid:
                logger.warning(f"create_article: validation failed — {result.errors}")
                return {
                    "success": False,
                    "validation_errors": result.errors,
                    "validation_warnings": result.warnings,
                }
            if result.warnings:
                logger.info(f"create_article: validation warnings — {result.warnings}")

        ws = self._require_connection()
        try:
            response = await create_article(ws, title, body, cover_path=cover_path, page=self._page)
            self._record_guard("post", success=response.get("success", False))
            return response
        except Exception as e:
            self._record_guard("post", success=False, error=str(e))
            raise

    async def quote_repost(
        self, post_id: str, comment: str = "", skip_validation: bool = False,
    ) -> dict[str, Any]:
        """Quote-repost a post with optional comment.

        Validates quote comment before publishing if comment is non-empty.

        Returns:
            {success, original_post_id} or {success: False, validation_errors}
        """
        allowed, reason = await self._check_guard("quote_repost")
        if not allowed:
            return {"success": False, "error": f"Guard denied: quote_repost — {reason}"}

        if comment and not skip_validation:
            result = validate_quote(comment)
            if not result.valid:
                logger.warning(f"quote_repost: validation failed — {result.errors}")
                return {
                    "success": False,
                    "validation_errors": result.errors,
                    "validation_warnings": result.warnings,
                }

        ws = self._require_connection()
        try:
            response = await repost(ws, post_id, comment=comment, page=self._page)
            self._record_guard("quote_repost", success=response.get("success", False))
            return response
        except Exception as e:
            self._record_guard("quote_repost", success=False, error=str(e))
            raise

    async def follow_user(self, post_id: str) -> dict[str, Any]:
        """Follow the author of a post. Skips if already following.

        Returns:
            {success, post_id, action: "followed"|"already_following"|"skipped"}
        """
        allowed, reason = await self._check_guard("follow")
        if not allowed:
            return {"success": False, "error": f"Guard denied: follow — {reason}"}

        ws = self._require_connection()
        try:
            response = await follow_author(ws, post_id, page=self._page)
            self._record_guard("follow", success=response.get("success", False))
            return response
        except Exception as e:
            self._record_guard("follow", success=False, error=str(e))
            raise

    async def engage_post(
        self,
        post_id: str,
        like: bool = True,
        comment: str | None = None,
        follow: bool = False,
    ) -> dict[str, Any]:
        """Engage with a post in one visit: like + comment + follow.

        Opens the post once, does everything, closes. Much more efficient
        than calling like_post + comment_on_post + follow_user separately.

        Returns:
            {success, liked, commented, followed, post_id, errors: []}
        """
        ws = self._require_connection()
        result = await engage_post(
            ws, post_id, like=like, comment_text=comment, follow=follow, page=self._page
        )

        # Record each sub-action in guard
        if result.get("liked"):
            self._record_guard("like", success=True)
        if result.get("commented"):
            self._record_guard("comment", success=True)
        if result.get("followed"):
            self._record_guard("follow", success=True)

        for err in result.get("errors", []):
            if err.startswith("like:"):
                self._record_guard("like", success=False, error=err)
            elif err.startswith("comment:"):
                self._record_guard("comment", success=False, error=err)
            elif err.startswith("follow:"):
                self._record_guard("follow", success=False, error=err)

        return result

    async def like_post(self, post_id: str) -> dict[str, Any]:
        """Like a post via browser click.

        Returns:
            {success, post_id}
        """
        allowed, reason = await self._check_guard("like")
        if not allowed:
            return {"success": False, "error": f"Guard denied: like — {reason}"}

        ws = self._require_connection()
        # Like via browser — navigate to post and click like button
        from src.session import page_map

        page = self._page
        try:
            post_url = page_map.POST_URL_TEMPLATE.format(post_id=post_id)
            await page.goto(post_url, wait_until="domcontentloaded", timeout=60_000)
            await asyncio.sleep(5)
            await warm_up(page)

            # Try detail-level like first (comment pages), then card-level (posts)
            detail_like = page.locator(page_map.COMMENT_DETAIL_LIKE).first
            card_like = page.locator(page_map.POST_LIKE_BUTTON).first

            try:
                await detail_like.wait_for(state="visible", timeout=3_000)
                await detail_like.scroll_into_view_if_needed()
                await mouse_move_to(page, page_map.COMMENT_DETAIL_LIKE)
                await asyncio.sleep(1)
                await detail_like.click()
                logger.info(f"Liked comment {post_id} (detail-thumb-up)")
            except Exception:
                await card_like.wait_for(state="visible", timeout=10_000)
                await card_like.scroll_into_view_if_needed()
                await mouse_move_to(page, page_map.POST_LIKE_BUTTON)
                await asyncio.sleep(1)
                await card_like.click()
                logger.info(f"Liked post {post_id} (thumb-up-button)")

            await asyncio.sleep(3)
            self._record_guard("like", success=True)
            return {"success": True, "post_id": post_id}
        except Exception as e:
            logger.error(f"Like failed on {post_id}: {e}")
            self._record_guard("like", success=False, error=str(e))
            return {"success": False, "error": str(e)}


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
        import os
        import time

        self._require_connection()
        page = self._page

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
        import os
        import time

        self._require_connection()
        page = self._page

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


class SDKError(Exception):
    """Raised when SDK operation fails."""
    pass
