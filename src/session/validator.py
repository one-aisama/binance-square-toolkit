"""Credential validator — tests if harvested credentials are still alive."""

import httpx
import logging

logger = logging.getLogger("bsq.session")

# This endpoint is lightweight and requires auth — good for validation
VALIDATION_URL = "https://www.binance.com/bapi/composite/v1/friendly/pgc/card/fearGreedHighestSearched"


async def validate_credentials(cookies: dict[str, str], headers: dict[str, str]) -> bool:
    """Make a test request to check if credentials are still valid.

    Args:
        cookies: dict of cookie name→value pairs
        headers: dict of bapi headers (csrftoken, bnc-uuid, etc.)

    Returns:
        True if credentials work, False otherwise.
    """
    try:
        # Build cookie header string
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
        request_headers = {
            "content-type": "application/json",
            "clienttype": "web",
            "lang": "en",
            "cookie": cookie_str,
        }
        # Add captured headers
        for key in ("csrftoken", "bnc-uuid", "device-info", "user-agent", "bnc-location"):
            if key in headers:
                request_headers[key] = headers[key]

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                VALIDATION_URL,
                json={},
                headers=request_headers,
                timeout=15.0,
                follow_redirects=False,
            )
            if resp.status_code == 200:
                data = resp.json()
                is_valid = data.get("success", False) or data.get("code") == "000000"
                if is_valid:
                    logger.debug("Credential validation passed")
                else:
                    logger.warning(f"Credential validation failed: {data.get('code')} {data.get('message', '')}")
                return is_valid
            else:
                logger.warning(f"Credential validation: HTTP {resp.status_code}")
                return False
    except Exception as e:
        logger.warning(f"Credential validation error: {e}")
        return False
