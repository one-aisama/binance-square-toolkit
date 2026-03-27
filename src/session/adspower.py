import httpx
import asyncio
import logging

logger = logging.getLogger("bsq.session")

RETRYABLE_ERRORS = (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError)


class AdsPowerClient:
    """Client for AdsPower Local API to start/stop browser profiles."""

    def __init__(
        self,
        base_url: str = "http://local.adspower.net:50325",
        timeout_start: float = 60.0,
        timeout_stop: float = 30.0,
        timeout_status: float = 20.0,
        retry_attempts: int = 2,
        retry_backoff: float = 0.5,
    ):
        self._base_url = base_url.rstrip("/")
        self._timeout_start = timeout_start
        self._timeout_stop = timeout_stop
        self._timeout_status = timeout_status
        self._retry_attempts = retry_attempts
        self._retry_backoff = retry_backoff

    async def get_status(self) -> dict:
        """Check if AdsPower is running."""
        return await self._request("GET", "/status", timeout=self._timeout_status)

    async def start_browser(self, user_id: str) -> dict:
        """Start browser for a profile. Returns ws endpoint and webdriver path.

        Returns dict with keys:
        - ws: str — WebSocket puppeteer endpoint
        - debug_port: str — debug port
        - webdriver: str — path to chromedriver
        """
        resp = await self._request(
            "GET",
            "/api/v1/browser/start",
            timeout=self._timeout_start,
            params={"user_id": user_id, "open_tabs": "0", "ip_tab": "0"},
        )
        data = resp.get("data", {})
        ws_info = data.get("ws", {})
        return {
            "ws": ws_info.get("puppeteer", ""),
            "debug_port": data.get("debug_port", ""),
            "webdriver": data.get("webdriver", ""),
        }

    async def stop_browser(self, user_id: str) -> dict:
        """Stop browser for a profile."""
        return await self._request(
            "GET",
            "/api/v1/browser/stop",
            timeout=self._timeout_stop,
            params={"user_id": user_id},
        )

    async def _request(
        self, method: str, path: str, timeout: float, params: dict = None
    ) -> dict:
        """Make HTTP request to AdsPower API with retry logic."""
        url = f"{self._base_url}{path}"
        last_error = None

        for attempt in range(1, self._retry_attempts + 1):
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.request(
                        method, url, params=params, timeout=timeout
                    )
                    resp.raise_for_status()
                    data = resp.json()

                    if data.get("code") != 0:
                        raise AdsPowerError(
                            f"AdsPower API error: {data.get('msg', 'unknown')}"
                        )

                    return data

            except RETRYABLE_ERRORS as e:
                last_error = e
                if attempt < self._retry_attempts:
                    wait = self._retry_backoff * (2 ** (attempt - 1))
                    logger.warning(
                        f"AdsPower request failed (attempt {attempt}/{self._retry_attempts}): {e}. "
                        f"Retrying in {wait}s..."
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(
                        f"AdsPower request failed after {self._retry_attempts} attempts: {e}"
                    )

        raise AdsPowerError(f"Request to {path} failed after {self._retry_attempts} attempts: {last_error}")


class AdsPowerError(Exception):
    """Raised when AdsPower API returns an error or is unreachable."""
    pass
