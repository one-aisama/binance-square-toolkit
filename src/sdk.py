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
import os
from typing import Any

import httpx

from src.runtime.guard import ActionGuard, Verdict

from src.session.browser_actions import (
    create_post,
    create_article,
    repost,
)
from src.session.browser_engage import (
    comment_on_post,
    engage_post,
    like_post as _browser_like_post,
    follow_author,
)
from src.session.browser_data import (
    collect_feed_posts,
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

logger = logging.getLogger("bsq.sdk")

ADSPOWER_BASE = "http://local.adspower.net:50325"


from src.sdk_screenshot import SDKScreenshotMixin, SDKError


class BinanceSquareSDK(SDKScreenshotMixin):
    """Unified SDK for AI agent to manage Binance Square profile.

    Agent uses this as the single entry point. All browser/API details hidden.
    """

    def __init__(
        self,
        profile_serial: str = "1",
        account_id: str = "default",
        db_path: str = "data/bsq.db",
        max_session_actions: int = 80,
        session_minimum: dict[str, int] | None = None,
        profile_username: str | None = None,
        adspower_base_url: str | None = None,
    ):
        self._serial = profile_serial
        self._account_id = account_id
        self._db_path = db_path
        self._max_session_actions = max_session_actions
        self._session_minimum = session_minimum or {"like": 20, "comment": 20, "post": 3}
        self._profile_username = profile_username
        self._adspower_base_url = adspower_base_url or os.getenv("BSQ_ADSPOWER_BASE_URL") or ADSPOWER_BASE
        self._ws_endpoint: str | None = None
        self._guard: ActionGuard | None = None
        self._pw = None
        self._browser = None
        self._page = None

    # ---- Connection ----

    async def connect(self) -> None:
        """Connect to AdsPower browser profile. Must be called before any action."""
        base_url = self._adspower_base_url

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{base_url}/api/v1/browser/active",
                params={"serial_number": self._serial},
            )
            data = resp.json()

        if data.get("code") == 0 and data.get("data", {}).get("status") == "Active":
            self._ws_endpoint = data["data"]["ws"]["puppeteer"]
            logger.info("Connected to active profile %s via %s", self._serial, base_url)
            await self._init_persistent_page()
            self._init_guard()
            return

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(
                f"{base_url}/api/v1/browser/start",
                params={"user_id": "", "serial_number": self._serial, "open_tabs": "0"},
            )
            data = resp.json()

        if data.get("code") != 0:
            raise SDKError(f"Failed to start profile {self._serial}: {data.get('msg')}")

        self._ws_endpoint = data["data"]["ws"]["puppeteer"]
        logger.info("Started and connected to profile %s via %s", self._serial, base_url)
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
            max_session_actions=self._max_session_actions,
            session_minimum=self._session_minimum,
        )
        logger.info(f"Guard initialized for {self._account_id}")

    async def _init_persistent_page(self) -> None:
        """Create persistent Playwright connection. One page for entire session."""
        from playwright.async_api import async_playwright
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.connect_over_cdp(self._ws_endpoint)
        context = self._browser.contexts[0] if self._browser.contexts else await self._browser.new_context()
        self._page = context.pages[0] if context.pages else await context.new_page()
        logger.info("Persistent page ready (reused existing tab)")

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


    def get_session_stats(self) -> dict[str, Any]:
        """Expose current guard/session statistics for reviewers and loop runners."""
        if self._guard:
            return self._guard.get_session_stats()
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

    async def _load_live_recent_posts(self) -> list[str]:
        """Load recent profile posts for duplicate and diversity checks."""
        if not self._profile_username:
            return []

        try:
            profile = await self.get_user_profile(self._profile_username)
        except Exception as exc:
            logger.warning(
                "create_post: failed to load recent profile posts for %s — %s",
                self._profile_username,
                exc,
            )
            return []

        recent_posts: list[str] = []
        for post in profile.get("recent_posts", []):
            preview = str(post.get("text_preview", "")).strip()
            if preview:
                recent_posts.append(preview)
        return recent_posts

    def _merge_recent_posts(self, provided: list[str] | None, live_recent: list[str]) -> list[str]:
        merged: list[str] = []
        for item in list(provided or []) + list(live_recent):
            preview = str(item or '').strip()
            if preview and preview not in merged:
                merged.append(preview)
        return merged

    # ---- Actions ----
    async def comment_on_post(
        self, post_id: str, text: str, skip_validation: bool = False,
    ) -> dict[str, Any]:
        """Post a comment on a specific post with guarded follow escalation."""
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

        allow_follow_reply, follow_reason = await self._check_guard("follow")
        ws = self._require_connection()
        try:
            response = await comment_on_post(
                ws,
                post_id,
                text,
                page=self._page,
                allow_follow_reply=allow_follow_reply,
            )
            if not allow_follow_reply and not response.get("followed"):
                skipped = list(response.get("skipped_actions") or [])
                skipped.append(f"follow: {follow_reason}")
                response = {**response, "skipped_actions": skipped}
            self._record_guard("comment", success=response.get("success", False), error=response.get("error"))
            if response.get("followed"):
                self._record_guard("follow", success=True)
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
            coin: Optional coin ticker to attach chart card (e.g. "BTC")
            sentiment: Optional "bullish" or "bearish" for chart-card posts
            image_path: Optional local file path for a single custom image
            recent_posts: Optional list of recent post texts for duplicate check
            skip_validation: Skip content validation (default False)

        Returns:
            {success, post_id, response} or {success: False, validation_errors, validation_warnings}
        """
        # coin tag + image_path allowed (tag appears alongside custom image)
        # coin tag + no image = chart card added automatically
        # sentiment requires coin tag
        if sentiment and not coin:
            return {
                "success": False,
                "validation_errors": ["Sentiment requires a coin tag"],
                "validation_warnings": [],
            }

        allowed, reason = await self._check_guard("post")
        if not allowed:
            return {"success": False, "error": f"Guard denied: post — {reason}"}

        live_recent_posts = await self._load_live_recent_posts()
        recent_posts = self._merge_recent_posts(recent_posts, live_recent_posts)

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
            response = await create_post(
                ws,
                text,
                coin=coin,
                sentiment=sentiment,
                image_path=image_path,
                page=self._page,
            )
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
        """Engage with a post in one visit: like + comment + follow."""
        comment_text = (comment or "").strip() or None
        validation_warnings: list[str] = []
        if comment_text:
            validation = validate_comment(comment_text)
            if not validation.valid:
                return {
                    "success": False,
                    "post_id": post_id,
                    "liked": False,
                    "commented": False,
                    "followed": False,
                    "errors": [],
                    "validation_errors": validation.errors,
                    "validation_warnings": validation.warnings,
                }
            validation_warnings = validation.warnings
            if validation_warnings:
                logger.info(f"engage_post: validation warnings — {validation_warnings}")

        allowed_like = like
        allowed_comment = comment_text
        allowed_follow = follow
        skipped_actions: list[str] = []

        if like:
            like_allowed, like_reason = await self._check_guard("like")
            if not like_allowed:
                allowed_like = False
                skipped_actions.append(f"like: {like_reason}")

        allow_follow_reply = True
        follow_reason = ""
        if comment_text or follow:
            allow_follow_reply, follow_reason = await self._check_guard("follow")
            if follow and not allow_follow_reply:
                allowed_follow = False
                skipped_actions.append(f"follow: {follow_reason}")

        if comment_text:
            comment_allowed, comment_reason = await self._check_guard("comment")
            if not comment_allowed:
                allowed_comment = None
                skipped_actions.append(f"comment: {comment_reason}")

        if not any([allowed_like, allowed_comment, allowed_follow]):
            return {
                "success": False,
                "post_id": post_id,
                "liked": False,
                "commented": False,
                "followed": False,
                "errors": skipped_actions,
                "skipped_actions": skipped_actions,
                "validation_warnings": validation_warnings,
                "error": "Guard denied all requested engagement actions",
            }

        ws = self._require_connection()
        result = await engage_post(
            ws,
            post_id,
            like=allowed_like,
            comment_text=allowed_comment,
            follow=allowed_follow,
            page=self._page,
            allow_follow_reply=allow_follow_reply,
        )

        if skipped_actions:
            result = {**result, "skipped_actions": skipped_actions}
        if validation_warnings:
            result = {**result, "validation_warnings": validation_warnings}
        if not allow_follow_reply and not result.get("followed") and comment_text:
            skipped = list(result.get("skipped_actions") or [])
            if not any(entry.startswith("follow:") for entry in skipped):
                skipped.append(f"follow: {follow_reason}")
            result = {**result, "skipped_actions": skipped}

        errors = list(result.get("errors") or [])
        generic_error = str(result.get("error") or "")

        def prefixed_error(prefix: str) -> str | None:
            for entry in errors:
                if entry.startswith(f"{prefix}:"):
                    return entry
            return None

        if allowed_like:
            if result.get("liked"):
                self._record_guard("like", success=True)
            else:
                error = prefixed_error("like") or generic_error or None
                if error:
                    self._record_guard("like", success=False, error=error)

        if allowed_comment:
            if result.get("commented"):
                self._record_guard("comment", success=True)
            else:
                error = prefixed_error("comment") or generic_error or result.get("reply_limit_message")
                if error or result.get("error_code") in {"reply_limit_exceeded", "follow_required"}:
                    self._record_guard("comment", success=False, error=str(error or result.get("error_code")))

        if result.get("followed"):
            self._record_guard("follow", success=True)
        elif allowed_follow:
            error = prefixed_error("follow") or generic_error or None
            if error:
                self._record_guard("follow", success=False, error=error)

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
        try:
            response = await _browser_like_post(ws, post_id, page=self._page)
            self._record_guard("like", success=response.get("success", False))
            return response
        except Exception as e:
            self._record_guard("like", success=False, error=str(e))
            raise


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

