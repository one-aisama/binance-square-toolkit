"""BapiClient — single point of contact with Binance bapi."""

import asyncio
import time
import logging
from typing import Any

import httpx

from src.session.credential_store import CredentialStore
from src.bapi import endpoints

logger = logging.getLogger("bsq.bapi")

RETRYABLE_STATUS_CODES = {429, 500, 502, 503}


class BapiClient:
    """HTTP client for Binance bapi with credential injection, retry, and rate limiting."""

    def __init__(
        self,
        account_id: str,
        credential_store: CredentialStore,
        base_url: str = "https://www.binance.com",
        rate_limit_rpm: int = 30,
        retry_attempts: int = 3,
        retry_backoff: float = 1.0,
    ):
        self._account_id = account_id
        self._credential_store = credential_store
        self._base_url = base_url.rstrip("/")
        self._min_interval = 60.0 / rate_limit_rpm
        self._retry_attempts = retry_attempts
        self._retry_backoff = retry_backoff
        self._last_request_time: float = 0.0

    async def get(self, path: str, params: dict | None = None) -> dict:
        """Make a GET request to bapi."""
        return await self._request("GET", path, params=params)

    async def post(self, path: str, data: dict | None = None) -> dict:
        """Make a POST request to bapi."""
        return await self._request("POST", path, json_data=data)

    async def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json_data: dict | None = None,
    ) -> dict:
        """Core request method with credential injection, rate limiting, retry."""
        # Rate limiting
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)

        # Load credentials
        cred = await self._credential_store.load(self._account_id)
        if cred is None:
            raise BapiCredentialError(f"No credentials found for {self._account_id}")

        cookies = cred["cookies"]
        headers = cred["headers"]

        # Build request headers — pass through ALL captured headers
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
        request_headers: dict[str, str] = {
            "content-type": "application/json",
            "cookie": cookie_str,
        }
        # Pass through all harvested headers (csrftoken, bnc-uuid, device-info,
        # fvideo-id, fvideo-token, clienttype, lang, bnc-location, etc.)
        for key, value in headers.items():
            if key != "cookie":  # cookie already set above
                request_headers[key] = value

        url = f"{self._base_url}{path}"
        last_error: Exception | None = None

        for attempt in range(1, self._retry_attempts + 1):
            try:
                async with httpx.AsyncClient() as client:
                    if method == "GET":
                        resp = await client.get(url, params=params, headers=request_headers, timeout=30.0)
                    else:
                        resp = await client.post(url, json=json_data or {}, headers=request_headers, timeout=30.0)

                self._last_request_time = time.monotonic()

                # Handle auth errors
                if resp.status_code in (401, 403):
                    logger.warning(f"Auth error {resp.status_code} for {self._account_id} on {path}")
                    await self._credential_store.invalidate(self._account_id)
                    raise BapiCredentialError(
                        f"Credentials expired for {self._account_id} (HTTP {resp.status_code})"
                    )

                # Handle retryable errors
                if resp.status_code in RETRYABLE_STATUS_CODES:
                    last_error = BapiRequestError(f"HTTP {resp.status_code} on {path}")
                    if attempt < self._retry_attempts:
                        wait = self._retry_backoff * (2 ** (attempt - 1))
                        logger.warning(f"Retryable error on {path} (attempt {attempt}): {resp.status_code}")
                        await asyncio.sleep(wait)
                        continue
                    raise last_error

                resp.raise_for_status()

                data = resp.json()
                logger.debug(f"bapi {method} {path} -> {data.get('code', '?')}")
                return data

            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_error = e
                if attempt < self._retry_attempts:
                    wait = self._retry_backoff * (2 ** (attempt - 1))
                    logger.warning(f"Network error on {path} (attempt {attempt}): {e}")
                    await asyncio.sleep(wait)
                else:
                    raise BapiRequestError(f"Request to {path} failed after {self._retry_attempts} attempts: {e}")

        raise BapiRequestError(f"Request to {path} failed: {last_error}")

    # ---- Convenience methods: Parsing ----

    async def get_feed_recommend(self, page: int = 1, page_size: int = 20) -> list[dict]:
        """Get recommended feed posts."""
        body = {"pageIndex": page, "pageSize": page_size, "scene": "web-homepage", "contentIds": []}
        data = await self.post(endpoints.FEED_RECOMMEND, body)
        if isinstance(data.get("data"), dict):
            # Response uses "vos" key, not "list"
            return data["data"].get("vos", data["data"].get("list", []))
        return []

    async def get_top_articles(self, page: int = 1, page_size: int = 20) -> list[dict]:
        """Get top/trending articles."""
        data = await self.get(endpoints.TOP_ARTICLES, {"pageIndex": page, "pageSize": page_size, "type": "1"})
        if isinstance(data.get("data"), dict):
            return data["data"].get("vos", data["data"].get("list", []))
        return []

    async def get_fear_greed(self) -> dict:
        """Get fear & greed index + popular coins."""
        data = await self.post(endpoints.FEAR_GREED, {})
        return data.get("data", {}) if isinstance(data.get("data"), dict) else {}

    async def get_hot_hashtags(self) -> list[dict]:
        """Get trending hashtags."""
        data = await self.get(endpoints.HOT_HASHTAGS)
        return data.get("data", []) if isinstance(data.get("data"), list) else []

    # ---- Convenience methods: Publishing & Activity ----
    # Exact endpoints TBD after discovery — these are stubs

    async def create_post(self, text: str, hashtags: list[str] | None = None) -> dict:
        """Create a new post on Binance Square. Endpoint TBD after discovery."""
        # TODO: Replace with actual endpoint after discovery
        raise NotImplementedError("Post creation endpoint not yet discovered")

    async def like_post(self, post_id: str, card_type: str = "BUZZ_SHORT") -> dict:
        """Like a post on Binance Square."""
        return await self.post(endpoints.LIKE_POST, {"id": post_id, "cardType": card_type})

    async def comment_post(self, post_id: str, text: str) -> dict:
        """Comment on a post. NOTE: Comments require browser automation, not httpx.
        Use browser_actions.comment_on_post() instead.
        This method exists for interface compatibility."""
        raise NotImplementedError(
            "Comments require browser automation. Use browser_actions.comment_on_post(ws_endpoint, post_id, text)"
        )

    async def repost(self, post_id: str) -> dict:
        """Repost a post. Endpoint TBD after discovery."""
        raise NotImplementedError("Repost endpoint not yet discovered")


class BapiClientError(Exception):
    """Base exception for BapiClient errors."""
    pass


class BapiCredentialError(BapiClientError):
    """Raised when credentials are missing or expired."""
    pass


class BapiRequestError(BapiClientError):
    """Raised when a bapi request fails after retries."""
    pass
