"""Playwright CDP credential harvester for Binance Square."""

import asyncio
import logging
import time
from typing import Any

from playwright.async_api import async_playwright, Response as PlaywrightResponse

logger = logging.getLogger("bsq.session")


async def harvest_credentials(ws_endpoint: str) -> dict[str, Any]:
    """Connect to AdsPower browser via CDP, navigate to Binance Square,
    capture bapi request cookies and headers.

    Args:
        ws_endpoint: WebSocket endpoint from AdsPower (ws://127.0.0.1:PORT/devtools/...)

    Returns:
        dict with keys:
        - cookies: dict[str, str] — name→value mapping of binance.com cookies
        - headers: dict[str, str] — captured bapi headers (csrftoken, bnc-uuid, device-info, user-agent, etc.)
        - discovered_endpoints: list[dict] — all bapi endpoints seen during navigation
    """
    captured_requests: list[dict[str, Any]] = []
    captured_headers: dict[str, str] = {}

    async with async_playwright() as p:
        logger.info(f"Connecting to browser via CDP: {ws_endpoint[:50]}...")
        try:
            browser = await p.chromium.connect_over_cdp(ws_endpoint)
        except Exception as exc:
            raise RuntimeError(f"Failed to connect via CDP: {exc}")

        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = context.pages[0] if context.pages else await context.new_page()

        # Network interception — capture bapi responses
        async def on_response(response: PlaywrightResponse) -> None:
            if "/bapi/" not in response.url:
                return
            request = response.request
            try:
                req_headers = dict(request.headers)
            except Exception:
                req_headers = {}

            # Extract ALL relevant headers from bapi requests
            HEADER_KEYS = (
                "csrftoken", "bnc-uuid", "device-info", "clienttype", "lang",
                "bnc-location", "bnc-time-zone", "fvideo-id", "fvideo-token",
                "versioncode", "x-passthrough-token", "x-trace-id", "x-ui-request-trace",
            )
            for key in HEADER_KEYS:
                if key not in captured_headers and req_headers.get(key):
                    captured_headers[key] = req_headers[key]

            # Store endpoint info
            url = response.url
            path = url.split("?")[0]
            bapi_idx = path.find("/bapi/")
            if bapi_idx >= 0:
                captured_requests.append({
                    "method": request.method,
                    "path": path[bapi_idx:],
                    "status": response.status,
                    "timestamp": time.time(),
                })

        page.on("response", on_response)

        # Navigate to Binance Square
        logger.info("Navigating to Binance Square...")
        try:
            await page.goto("https://www.binance.com/en/square", wait_until="domcontentloaded", timeout=60_000)
        except Exception as exc:
            logger.warning(f"Navigation exception (continuing): {exc}")

        try:
            await page.wait_for_load_state("networkidle", timeout=30_000)
        except Exception:
            logger.warning("Network did not reach idle — proceeding with captured data.")

        # Extra time for lazy-loaded bapi calls
        await asyncio.sleep(3)

        # Extract cookies
        all_cookies = await context.cookies()
        binance_cookies = {
            c["name"]: c["value"]
            for c in all_cookies
            if "binance" in c.get("domain", "")
        }

        # Get user agent
        user_agent = await page.evaluate("navigator.userAgent")
        captured_headers["user-agent"] = user_agent

        # Don't close browser — AdsPower manages it

    # Deduplicate discovered endpoints
    seen = set()
    unique_endpoints = []
    for req in captured_requests:
        key = f"{req['method']}:{req['path']}"
        if key not in seen:
            seen.add(key)
            unique_endpoints.append({"method": req["method"], "path": req["path"]})

    logger.info(
        f"Harvested: {len(binance_cookies)} cookies, "
        f"{len(captured_headers)} headers, "
        f"{len(unique_endpoints)} unique bapi endpoints"
    )

    return {
        "cookies": binance_cookies,
        "headers": captured_headers,
        "discovered_endpoints": unique_endpoints,
    }
