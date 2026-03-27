"""
CDP Spike Script — Binance Square Content Farm
===============================================
Validates the core CDP-First assumption:
  1. Start AdsPower profile via Local API
  2. Connect Playwright to the browser via CDP
  3. Navigate to Binance Square, intercept ALL bapi requests
  4. Extract cookies and key headers
  5. Stop the browser
  6. Reproduce key bapi requests via httpx
  7. Save all discovered endpoints + credentials to spike_results.json

Usage:
    python scripts/spike_cdp.py <adspower_profile_id>
"""

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from playwright.async_api import async_playwright, Response as PlaywrightResponse

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ADSPOWER_BASE = "http://local.adspower.net:50325"
BINANCE_SQUARE_URL = "https://www.binance.com/en/square"
BINANCE_BASE = "https://www.binance.com"

RESULTS_PATH = Path(__file__).parent / "spike_results.json"

# Known bapi endpoints to validate via httpx after harvesting
ENDPOINTS_TO_REPRODUCE = [
    {
        "label": "Feed Recommend (POST)",
        "method": "POST",
        "path": "/bapi/composite/v9/friendly/pgc/feed/feed-recommend/list",
        "body": {
            "pageIndex": 1,
            "pageSize": 20,
        },
    },
    {
        "label": "Top Articles (GET)",
        "method": "GET",
        "path": "/bapi/composite/v3/friendly/pgc/content/article/list",
        "params": {"pageIndex": "1", "pageSize": "20", "type": "1"},
    },
    {
        "label": "Fear & Greed (GET)",
        "method": "GET",
        "path": "/bapi/composite/v1/friendly/pgc/card/fearGreedHighestSearched",
        "params": {},
    },
]

# ANSI color codes (work on Windows 10+ with ANSI enabled)
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def enable_windows_ansi() -> None:
    """Enable ANSI escape codes on Windows by setting the console mode."""
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass  # Non-Windows or no ctypes — ignore


def ok(msg: str) -> None:
    print(f"{GREEN}[PASS]{RESET} {msg}")


def fail(msg: str) -> None:
    print(f"{RED}[FAIL]{RESET} {msg}")


def info(msg: str) -> None:
    print(f"{CYAN}[INFO]{RESET} {msg}")


def warn(msg: str) -> None:
    print(f"{YELLOW}[WARN]{RESET} {msg}")


def section(title: str) -> None:
    print(f"\n{BOLD}{CYAN}{'=' * 60}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'=' * 60}{RESET}")


# ---------------------------------------------------------------------------
# AdsPower API
# ---------------------------------------------------------------------------

async def start_adspower_browser(client: httpx.AsyncClient, profile_id: str) -> dict[str, Any]:
    """
    Start an AdsPower browser profile and return the response data dict.

    Returns:
        dict with keys: ws.puppeteer, debug_port, webdriver
    Raises:
        RuntimeError on failure.
    """
    info(f"Starting AdsPower profile: {profile_id}")
    try:
        resp = await client.get(
            f"{ADSPOWER_BASE}/api/v1/browser/start",
            params={"user_id": profile_id},
            timeout=60.0,
        )
        resp.raise_for_status()
    except httpx.ConnectError:
        raise RuntimeError(
            "Cannot connect to AdsPower Local API at http://local.adspower.net:50325. "
            "Make sure AdsPower is running."
        )
    except httpx.TimeoutException:
        raise RuntimeError("AdsPower API timed out while starting browser (60s).")

    payload = resp.json()
    if payload.get("code") != 0:
        raise RuntimeError(
            f"AdsPower returned error code {payload.get('code')}: {payload.get('msg')}"
        )

    data = payload["data"]
    ws_endpoint: str = data["ws"]["puppeteer"]
    info(f"Browser started. WS endpoint: {ws_endpoint}")
    return data


async def stop_adspower_browser(client: httpx.AsyncClient, profile_id: str) -> None:
    """Stop the AdsPower browser profile."""
    info(f"Stopping AdsPower profile: {profile_id}")
    try:
        resp = await client.get(
            f"{ADSPOWER_BASE}/api/v1/browser/stop",
            params={"user_id": profile_id},
            timeout=30.0,
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") == 0:
            info("Browser stopped successfully.")
        else:
            warn(f"AdsPower stop returned code {payload.get('code')}: {payload.get('msg')}")
    except Exception as exc:
        warn(f"Failed to stop AdsPower browser: {exc}")


# ---------------------------------------------------------------------------
# CDP Credential Harvesting
# ---------------------------------------------------------------------------

async def harvest_credentials(ws_endpoint: str) -> dict[str, Any]:
    """
    Connect to the running browser via CDP, navigate to Binance Square,
    intercept all bapi network requests, extract cookies and key headers.

    Returns:
        {
            "captured_requests": [...],   # list of bapi request dicts
            "cookies": [...],             # all binance.com cookies
            "user_agent": str,
            "bnc_uuid": str | None,
            "csrftoken": str | None,
        }
    """
    captured_requests: list[dict[str, Any]] = []

    async with async_playwright() as pw:
        info("Connecting to browser via CDP...")
        try:
            browser = await pw.chromium.connect_over_cdp(ws_endpoint)
        except Exception as exc:
            raise RuntimeError(f"Failed to connect via CDP: {exc}")

        # Use existing context (AdsPower profile carries its own context)
        contexts = browser.contexts
        if contexts:
            context = contexts[0]
            info(f"Reusing existing browser context (pages: {len(context.pages)})")
        else:
            context = await browser.new_context()
            info("Created new browser context.")

        page = await context.new_page()

        # ----------------------------------------------------------------
        # Network interception — capture all bapi responses
        # ----------------------------------------------------------------

        async def on_response(response: PlaywrightResponse) -> None:
            """Store metadata for every /bapi/ response."""
            url: str = response.url
            if "/bapi/" not in url:
                return

            request = response.request
            try:
                req_headers = dict(request.headers)
            except Exception:
                req_headers = {}

            entry: dict[str, Any] = {
                "url": url,
                "method": request.method,
                "status": response.status,
                "request_headers": req_headers,
                "request_body": None,
                "response_body_preview": None,
                "timestamp": time.time(),
            }

            # Try to get request body (POST)
            try:
                post_data = request.post_data
                if post_data:
                    try:
                        entry["request_body"] = json.loads(post_data)
                    except json.JSONDecodeError:
                        entry["request_body"] = post_data
            except Exception:
                pass

            # Try to get response body preview (first 500 chars)
            try:
                body = await response.text()
                entry["response_body_preview"] = body[:500] if body else None
            except Exception:
                pass

            captured_requests.append(entry)

        page.on("response", on_response)

        # ----------------------------------------------------------------
        # Navigate to Binance Square and wait for network to settle
        # ----------------------------------------------------------------
        info(f"Navigating to {BINANCE_SQUARE_URL} ...")
        try:
            await page.goto(BINANCE_SQUARE_URL, wait_until="domcontentloaded", timeout=60_000)
        except Exception as exc:
            warn(f"Navigation raised an exception (will try to continue): {exc}")

        info("Waiting for network idle (up to 30s)...")
        try:
            await page.wait_for_load_state("networkidle", timeout=30_000)
        except Exception:
            warn("Network did not reach idle — proceeding with what was captured.")

        # Extra settle time to let lazy-loaded bapi calls fire
        await asyncio.sleep(3)

        # ----------------------------------------------------------------
        # Extract cookies
        # ----------------------------------------------------------------
        info("Extracting cookies from browser context...")
        all_cookies = await context.cookies()
        binance_cookies = [
            c for c in all_cookies if "binance.com" in c.get("domain", "")
        ]

        # ----------------------------------------------------------------
        # Extract key headers from captured bapi requests
        # ----------------------------------------------------------------
        user_agent: str = await page.evaluate("navigator.userAgent")
        bnc_uuid: str | None = None
        csrftoken: str | None = None
        device_info: str | None = None

        for req in captured_requests:
            headers = req.get("request_headers", {})
            if not bnc_uuid and headers.get("bnc-uuid"):
                bnc_uuid = headers["bnc-uuid"]
            if not csrftoken and headers.get("csrftoken"):
                csrftoken = headers["csrftoken"]
            if not device_info and headers.get("device-info"):
                device_info = headers["device-info"]
            if bnc_uuid and csrftoken:
                break

        # Try cookie-based csrftoken as fallback
        if not csrftoken:
            for c in binance_cookies:
                if c.get("name") == "csrftoken":
                    csrftoken = c.get("value")
                    break

        info(f"Captured {len(captured_requests)} bapi requests.")
        info(f"Binance cookies: {len(binance_cookies)} found.")
        info(f"bnc-uuid: {bnc_uuid or 'NOT FOUND'}")
        info(f"csrftoken: {csrftoken or 'NOT FOUND'}")
        info(f"User-Agent: {user_agent[:80]}...")

        # Don't close browser — AdsPower manages it, we just disconnect
        # browser.close() would kill the AdsPower session

    return {
        "captured_requests": captured_requests,
        "cookies": binance_cookies,
        "user_agent": user_agent,
        "bnc_uuid": bnc_uuid,
        "csrftoken": csrftoken,
        "device_info": device_info,
    }


# ---------------------------------------------------------------------------
# httpx Reproduction
# ---------------------------------------------------------------------------

def build_cookie_header(cookies: list[dict]) -> str:
    """Convert a list of cookie dicts (Playwright format) to a Cookie header string."""
    parts = [f"{c['name']}={c['value']}" for c in cookies if c.get("name")]
    return "; ".join(parts)


def build_bapi_headers(harvested: dict[str, Any]) -> dict[str, str]:
    """
    Assemble the required headers for bapi requests from harvested credentials.
    """
    headers: dict[str, str] = {
        "clienttype": "web",
        "content-type": "application/json",
        "lang": "en",
        "bnc-location": "KZ_COM",
        "user-agent": harvested.get("user_agent", ""),
    }
    if harvested.get("bnc_uuid"):
        headers["bnc-uuid"] = harvested["bnc_uuid"]
    if harvested.get("csrftoken"):
        headers["csrftoken"] = harvested["csrftoken"]
    if harvested.get("device_info"):
        headers["device-info"] = harvested["device_info"]

    cookie_str = build_cookie_header(harvested.get("cookies", []))
    if cookie_str:
        headers["cookie"] = cookie_str

    return headers


async def reproduce_requests(harvested: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Attempt to reproduce the known key bapi endpoints via httpx.
    Returns a list of result dicts with PASS/FAIL status.
    """
    section("Reproducing bapi Requests via httpx")

    headers = build_bapi_headers(harvested)
    results: list[dict[str, Any]] = []

    async with httpx.AsyncClient(
        base_url=BINANCE_BASE,
        headers=headers,
        timeout=30.0,
        follow_redirects=True,
    ) as client:
        for endpoint in ENDPOINTS_TO_REPRODUCE:
            label = endpoint["label"]
            method = endpoint["method"]
            path = endpoint["path"]
            info(f"Testing: {label}")

            result: dict[str, Any] = {
                "label": label,
                "method": method,
                "path": path,
                "status": None,
                "passed": False,
                "error": None,
                "response_preview": None,
            }

            try:
                if method == "GET":
                    resp = await client.get(path, params=endpoint.get("params", {}))
                elif method == "POST":
                    resp = await client.post(path, json=endpoint.get("body", {}))
                else:
                    raise ValueError(f"Unsupported method: {method}")

                result["status"] = resp.status_code

                # Try to parse response
                try:
                    body = resp.json()
                    result["response_preview"] = json.dumps(body)[:300]
                    # Binance bapi returns {"code": "000000"} on success
                    bapi_code = body.get("code")
                    result["passed"] = resp.status_code == 200 and (
                        bapi_code in ("000000", 0, "0") or bapi_code is None
                    )
                except Exception:
                    result["response_preview"] = resp.text[:300]
                    result["passed"] = resp.status_code == 200

            except httpx.ConnectError as exc:
                result["error"] = f"Connection error: {exc}"
            except httpx.TimeoutException:
                result["error"] = "Request timed out (30s)"
            except Exception as exc:
                result["error"] = f"Unexpected error: {exc}"

            if result["passed"]:
                ok(f"{label} — HTTP {result['status']}")
            else:
                error_detail = result["error"] or f"HTTP {result['status']}"
                if result.get("response_preview"):
                    error_detail += f" | {result['response_preview'][:120]}"
                fail(f"{label} — {error_detail}")

            results.append(result)

    return results


# ---------------------------------------------------------------------------
# Results Saving
# ---------------------------------------------------------------------------

def extract_unique_bapi_paths(captured: list[dict]) -> list[dict[str, str]]:
    """Deduplicate and summarize discovered bapi paths."""
    seen: dict[str, str] = {}  # method+path -> url
    for req in captured:
        url: str = req.get("url", "")
        method: str = req.get("method", "?")
        # Extract path (strip query string)
        path = url.split("?")[0]
        if "/bapi/" in path:
            # Normalize: take from /bapi/ onwards
            idx = path.find("/bapi/")
            bapi_path = path[idx:]
            key = f"{method}:{bapi_path}"
            if key not in seen:
                seen[key] = url
    return [
        {"method": k.split(":")[0], "path": k.split(":", 1)[1], "full_url": v}
        for k, v in seen.items()
    ]


def save_results(
    profile_id: str,
    harvested: dict[str, Any],
    reproduction_results: list[dict[str, Any]],
) -> None:
    """Save all spike results to spike_results.json."""
    unique_paths = extract_unique_bapi_paths(harvested["captured_requests"])

    output = {
        "profile_id": profile_id,
        "harvested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "credentials": {
            "bnc_uuid": harvested.get("bnc_uuid"),
            "csrftoken": harvested.get("csrftoken"),
            "device_info": harvested.get("device_info"),
            "user_agent": harvested.get("user_agent"),
            "cookies": harvested.get("cookies", []),
        },
        "discovered_bapi_endpoints": unique_paths,
        "captured_requests_count": len(harvested["captured_requests"]),
        "captured_requests": harvested["captured_requests"],
        "reproduction_results": reproduction_results,
    }

    RESULTS_PATH.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    info(f"Results saved to: {RESULTS_PATH}")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_summary(
    harvested: dict[str, Any],
    reproduction_results: list[dict[str, Any]],
) -> None:
    """Print the final summary to stdout."""
    section("Summary")

    unique_paths = extract_unique_bapi_paths(harvested["captured_requests"])
    passed = sum(1 for r in reproduction_results if r["passed"])
    total = len(reproduction_results)

    print(f"\n  Discovered bapi endpoints: {len(unique_paths)}")
    for ep in unique_paths:
        print(f"    {ep['method']:6} {ep['path']}")

    print(f"\n  Credentials harvested:")
    print(f"    bnc-uuid   : {harvested.get('bnc_uuid') or 'NOT FOUND'}")
    print(f"    csrftoken  : {harvested.get('csrftoken') or 'NOT FOUND'}")
    print(f"    cookies    : {len(harvested.get('cookies', []))} entries")

    print(f"\n  Reproduction results: {passed}/{total} PASSED")
    for r in reproduction_results:
        status_str = f"{GREEN}PASS{RESET}" if r["passed"] else f"{RED}FAIL{RESET}"
        print(f"    [{status_str}] {r['label']}")

    verdict = (
        f"{GREEN}CDP-First approach is VIABLE{RESET}"
        if passed > 0 and harvested.get("csrftoken") and harvested.get("bnc_uuid")
        else f"{RED}CDP-First approach needs INVESTIGATION{RESET}"
    )
    print(f"\n  Verdict: {verdict}")
    print(f"\n  Full details: {RESULTS_PATH}\n")


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

async def get_active_ws(client: httpx.AsyncClient, profile_id: str) -> str | None:
    """Check if browser is already active, return ws endpoint if so."""
    try:
        resp = await client.get(
            f"{ADSPOWER_BASE}/api/v1/browser/active",
            params={"user_id": profile_id},
            timeout=10.0,
        )
        data = resp.json()
        if data.get("code") == 0 and data.get("data", {}).get("status") == "Active":
            ws = data["data"].get("ws", {}).get("puppeteer", "")
            if ws:
                return ws
    except Exception:
        pass
    return None


async def main(profile_id: str) -> None:
    """Main async entry point for the CDP spike."""
    enable_windows_ansi()

    section(f"Binance Square CDP Spike — Profile: {profile_id}")

    browser_was_started = False

    async with httpx.AsyncClient() as adspower_client:

        # 1. Check if browser already active, if not — start it
        ws_endpoint = await get_active_ws(adspower_client, profile_id)
        if ws_endpoint:
            info(f"Browser already active. WS endpoint: {ws_endpoint}")
        else:
            try:
                browser_data = await start_adspower_browser(adspower_client, profile_id)
            except RuntimeError as exc:
                fail(str(exc))
                sys.exit(1)
            ws_endpoint = browser_data["ws"]["puppeteer"]
            browser_was_started = True

        # 2. Harvest credentials via CDP
        section("Harvesting Credentials via CDP")
        harvested: dict[str, Any] = {}
        try:
            harvested = await harvest_credentials(ws_endpoint)
        except RuntimeError as exc:
            fail(f"CDP harvesting failed: {exc}")
            if browser_was_started:
                await stop_adspower_browser(adspower_client, profile_id)
            sys.exit(1)
        except Exception as exc:
            fail(f"Unexpected error during CDP harvesting: {exc}")
            if browser_was_started:
                await stop_adspower_browser(adspower_client, profile_id)
            sys.exit(1)

        # 3. Only stop browser if WE started it
        if browser_was_started:
            section("Stopping AdsPower Browser")
            await stop_adspower_browser(adspower_client, profile_id)
        else:
            info("Skipping browser stop — it was already running before spike.")

    # 4. Reproduce requests via httpx (outside adspower_client context)
    if not harvested.get("cookies"):
        warn("No cookies were harvested — bapi reproduction will likely fail.")

    reproduction_results = await reproduce_requests(harvested)

    # 5. Save results
    section("Saving Results")
    save_results(profile_id, harvested, reproduction_results)

    # 6. Print summary
    print_summary(harvested, reproduction_results)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: python scripts/spike_cdp.py <adspower_profile_id>")
        sys.exit(1)

    profile_id = sys.argv[1]
    asyncio.run(main(profile_id))
