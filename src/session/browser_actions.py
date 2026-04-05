"""Browser-based publishing actions via Playwright CDP.

Used for operations that require client-side signature (posting, reposting)
and can't be done through pure httpx.

Engagement actions (like, comment, follow, engage) live in browser_engage.py.
"""

import asyncio
import logging
import re
from typing import Any

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError, async_playwright

from src.session import page_map
from src.runtime.behavior import warm_up, mouse_move_to

logger = logging.getLogger("bsq.session")




_REPLY_LIMIT_NEEDLES = (
    "[710000]",
    "limit exceeded",
    "users without assets in their wallets are limited to a maximum of 3 replies every 7 days",
)


async def _detect_reply_limit(page: Page) -> str | None:
    try:
        body_text = await page.locator("body").inner_text(timeout=2_000)
    except Exception:
        return None

    lowered = body_text.lower()
    for needle in _REPLY_LIMIT_NEEDLES:
        if needle.lower() in lowered:
            return needle
    return None

async def _connect_browser(ws_endpoint: str) -> tuple:
    """Connect to AdsPower browser and return (playwright, browser, page).

    For standalone use only. When called from SDK with persistent session,
    SDK passes page= directly and this function is not called.
    """
    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp(ws_endpoint)
    context = browser.contexts[0] if browser.contexts else await browser.new_context()
    page = context.pages[0] if context.pages else await context.new_page()
    return pw, browser, page



async def _get_page_or_use(ws_endpoint: str = None, *, page=None):
    """Get page: use provided page or connect to browser.
    Returns (pw_or_None, browser_or_None, page, needs_cleanup).
    """
    if page is not None:
        return None, None, page, False
    pw, browser, pg = await _connect_browser(ws_endpoint)
    return pw, browser, pg, True


def _normalize_compose_text(value: str | None) -> str:
    return " ".join(str(value or "").split()).strip()


def _post_button_state_is_enabled(
    *,
    aria_disabled: str | None,
    disabled_attr: str | None,
    class_name: str | None,
) -> bool:
    if str(aria_disabled or "").strip().lower() in {"true", "1"}:
        return False
    if disabled_attr is not None:
        return False
    lowered = str(class_name or "").lower()
    return "disabled" not in lowered and "inactive" not in lowered


def _ui_indicates_post_success(
    *,
    current_url: str,
    editor_text: str | None,
    original_text: str,
    button_enabled: bool,
) -> bool:
    if "/square/post/" in str(current_url or "").lower():
        return True

    normalized_editor = _normalize_compose_text(editor_text)
    normalized_original = _normalize_compose_text(original_text)
    if normalized_editor and normalized_original:
        marker = normalized_original[:80]
        if marker and marker in normalized_editor:
            return False
    return not normalized_editor and not button_enabled


async def _locator_is_enabled(locator: Any) -> bool:
    try:
        if await locator.is_enabled():
            return True
    except Exception:
        pass

    try:
        aria_disabled = await locator.get_attribute("aria-disabled")
    except Exception:
        aria_disabled = None
    try:
        disabled_attr = await locator.get_attribute("disabled")
    except Exception:
        disabled_attr = None
    try:
        class_name = await locator.get_attribute("class")
    except Exception:
        class_name = None

    return _post_button_state_is_enabled(
        aria_disabled=aria_disabled,
        disabled_attr=disabled_attr,
        class_name=class_name,
    )


async def _resolve_post_button(page: Page) -> Any:
    buttons = page.locator(page_map.COMPOSE_INLINE_POST_BUTTON)
    try:
        count = await buttons.count()
    except Exception:
        count = 0

    visible_candidates: list[Any] = []
    for index in range(max(count - 1, 0), -1, -1):
        button = buttons.nth(index)
        try:
            if not await button.is_visible():
                continue
        except Exception:
            continue
        if await _locator_is_enabled(button):
            return button
        visible_candidates.append(button)

    return visible_candidates[0] if visible_candidates else buttons.first


async def _wait_for_post_button_ready(button: Any, *, timeout_ms: int = 30_000) -> None:
    deadline = asyncio.get_running_loop().time() + (timeout_ms / 1000)
    while asyncio.get_running_loop().time() < deadline:
        try:
            await button.scroll_into_view_if_needed()
        except Exception:
            pass
        if await _locator_is_enabled(button):
            return
        await asyncio.sleep(0.5)
    raise TimeoutError(f"Post button did not become enabled within {timeout_ms}ms")


async def _get_compose_editor_text(page: Page) -> str:
    editor = page.locator(page_map.COMPOSE_EDITOR).first
    try:
        return await editor.inner_text(timeout=1_000)
    except Exception:
        try:
            return (await editor.text_content()) or ""
        except Exception:
            return ""


def _extract_post_id_from_url(url: str) -> str:
    match = re.search(r"/square/post/(\d+)", str(url or ""))
    return match.group(1) if match else ""


async def _post_submission_looks_confirmed(page: Page, *, original_text: str) -> tuple[bool, str]:
    editor_text = await _get_compose_editor_text(page)
    button = await _resolve_post_button(page)
    button_enabled = await _locator_is_enabled(button)
    confirmed = _ui_indicates_post_success(
        current_url=page.url,
        editor_text=editor_text,
        original_text=original_text,
        button_enabled=button_enabled,
    )
    return confirmed, _extract_post_id_from_url(page.url)


async def _click_post_and_wait_for_response(
    page: Page,
    *,
    button: Any,
    timeout_ms: int,
    dom_fallback: bool = False,
) -> dict[str, Any] | None:
    try:
        async with page.expect_response(lambda response: "content/add" in response.url, timeout=timeout_ms) as response_info:
            await button.scroll_into_view_if_needed()
            try:
                await button.hover()
            except Exception:
                pass
            await asyncio.sleep(1)
            if dom_fallback:
                await button.evaluate("(node) => node.click()")
            else:
                await button.click()

        response = await response_info.value
        try:
            payload = await response.json()
        except Exception:
            payload = {"success": response.status == 200, "status": response.status, "url": response.url}
        return payload
    except PlaywrightTimeoutError:
        return None

async def _type_with_hashtag_handling(page: Page, text: str, delay: int = 60):
    """Type text handling #hashtag and $CASHTAG autocomplete popups.

    After each #hashtag or $CASHTAG word, presses Escape to dismiss
    the autocomplete dropdown that would otherwise block the Post button.
    """
    parts = re.split(r"([#$])", text)
    i = 0
    while i < len(parts):
        part = parts[i]
        if part in ("#", "$"):
            tag_text = parts[i + 1] if i + 1 < len(parts) else ""
            tag_word = tag_text.split(" ")[0] if " " in tag_text else tag_text
            rest = tag_text[len(tag_word):]

            await page.keyboard.type(part, delay=delay)
            await page.keyboard.type(tag_word, delay=delay)
            await asyncio.sleep(0.5)
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.3)
            if rest:
                await page.keyboard.type(rest, delay=delay)
            i += 2  # skip delimiter + tag text
        else:
            if part:
                await page.keyboard.type(part, delay=delay)
            i += 1


async def create_post(
    ws_endpoint: str = None,
    text: str = "",
    coin: str | None = None,
    sentiment: str | None = None,
    image_path: str | None = None,
    *,
    page=None,
) -> dict[str, Any]:
    """Create a post on Binance Square via browser automation."""
    pw, browser, page, _cleanup = await _get_page_or_use(ws_endpoint, page=page)

    try:
        # coin + image_path allowed: image attached, chart card skipped, coin tag still works

        logger.info("Navigating to Binance Square...")
        await page.goto(page_map.SQUARE_URL, wait_until="domcontentloaded", timeout=60_000)
        await asyncio.sleep(5)
        await warm_up(page)

        editor = page.locator(page_map.COMPOSE_EDITOR).first
        await editor.wait_for(state="visible", timeout=15_000)
        await asyncio.sleep(1)
        await editor.click()
        await asyncio.sleep(1)

        await _type_with_hashtag_handling(page, text, delay=60)
        await asyncio.sleep(2)

        if image_path:
            await _attach_image_inline(page, image_path)

        # Add chart card only if no custom image (coin tag still works with image)
        if coin and not image_path:
            await _add_chart(page, coin)

        if sentiment:
            await _set_sentiment(page, sentiment)

        await asyncio.sleep(2)
        post_btn = await _resolve_post_button(page)
        await _wait_for_post_button_ready(post_btn)

        post_response = await _click_post_and_wait_for_response(
            page,
            button=post_btn,
            timeout_ms=15_000,
        )

        if not post_response:
            confirmed, post_id = await _post_submission_looks_confirmed(page, original_text=text)
            if confirmed:
                logger.info("Post created via UI confirmation%s", f": {post_id}" if post_id else "")
                return {
                    "success": True,
                    "post_id": post_id,
                    "response": {"success": True, "confirmation": "ui_state"},
                }

            logger.warning("Primary post click produced no publish response; retrying with DOM click")
            retry_btn = await _resolve_post_button(page)
            await _wait_for_post_button_ready(retry_btn, timeout_ms=5_000)
            post_response = await _click_post_and_wait_for_response(
                page,
                button=retry_btn,
                timeout_ms=15_000,
                dom_fallback=True,
            )

        if post_response and post_response.get("success"):
            post_id = str(post_response.get("data", {}).get("id", "") or _extract_post_id_from_url(page.url))
            logger.info(f"Post created: {post_id}")
            return {"success": True, "post_id": post_id, "response": post_response}
        if post_response:
            return {
                "success": False,
                "error": post_response.get("message", "Unknown"),
                "response": post_response,
            }

        for _ in range(10):
            confirmed, post_id = await _post_submission_looks_confirmed(page, original_text=text)
            if confirmed:
                logger.info("Post created via delayed UI confirmation%s", f": {post_id}" if post_id else "")
                return {
                    "success": True,
                    "post_id": post_id,
                    "response": {"success": True, "confirmation": "ui_state_delayed"},
                }
            await asyncio.sleep(1)

        logger.error("Post submission could not be confirmed from network responses")
        return {
            "success": False,
            "error": "Post submission could not be confirmed",
            "error_code": "publish_unconfirmed",
        }

    except Exception as e:
        logger.error(f"Post creation failed: {e}")
        return {"success": False, "error": str(e)}
    finally:
        if _cleanup and pw:
            await pw.stop()


async def _add_chart(page: Page, coin: str):
    """Click Add Chart button in compose toolbar, search for coin, select it.

    The chart popup lives inside a [data-tippy-root] container near the toolbar,
    NOT the site-wide search bar. We must scope all interactions to this popup.
    """
    try:
        logger.info(f"Adding chart for {coin}...")
        chart_btn = page.locator(page_map.COMPOSE_ADD_CHART).first
        await chart_btn.click()
        await asyncio.sleep(2)

        # The popup is the LAST tippy-root on the page (compose toolbar popup)
        popup = page.locator("[data-tippy-root]").last
        search = popup.locator("input").first
        await search.wait_for(state="visible", timeout=5_000)
        await search.fill(coin)
        await asyncio.sleep(2)

        # Click the coin row in dropdown (force=True to bypass overlay interception)
        coin_row = popup.locator(f'div.cursor-pointer:has-text("{coin}")').first
        await coin_row.click(force=True)
        await asyncio.sleep(2)
        logger.info(f"Chart for {coin} attached")
    except Exception as e:
        logger.warning(f"Failed to add chart for {coin}: {e}")


async def _set_sentiment(page: Page, sentiment: str):
    """Click bullish (green) or bearish (red) arrow."""
    try:
        logger.info(f"Setting sentiment: {sentiment}...")
        if sentiment.lower() == "bullish":
            arrow = page.locator(f".{page_map.COMPOSE_BULLISH_ARROW}").first
        else:
            arrow = page.locator(f".{page_map.COMPOSE_BEARISH_ARROW}").first
        await arrow.click()
        await asyncio.sleep(1)
        logger.info(f"Sentiment set: {sentiment}")
    except Exception as e:
        logger.warning(f"Failed to set sentiment: {e}")


async def _attach_image_inline(page: Page, image_path: str):
    """Attach image to inline post via hidden file input."""
    try:
        logger.info(f"Attaching image: {image_path}...")
        file_input = page.locator(page_map.COMPOSE_IMAGE_INPUT).first
        await file_input.set_input_files(image_path)
        await asyncio.sleep(3)
        logger.info("Image attached")
    except Exception as e:
        logger.warning(f"Failed to attach image: {e}")


async def create_article(
    ws_endpoint: str = None,
    title: str = "",
    body: str = "",
    cover_path: str | None = None,
    image_paths: list[str] | None = None,
    *,
    page=None,
) -> dict[str, Any]:
    """Create an article on Binance Square via browser automation.

    Args:
        ws_endpoint: WebSocket endpoint from AdsPower
        title: Article title
        body: Article body text
        cover_path: Optional local file path for cover image
        image_paths: Optional list of image paths to insert in body

    Returns:
        dict with success status
    """
    pw, browser, page, _cleanup = await _get_page_or_use(ws_endpoint, page=page)

    try:
        logger.info("Navigating to Binance Square...")
        await page.goto(page_map.SQUARE_URL, wait_until="domcontentloaded", timeout=60_000)
        await asyncio.sleep(5)
        await warm_up(page)

        # Dismiss cookie banner
        try:
            await page.locator("button#onetrust-reject-all-handler").click(timeout=3_000)
            await asyncio.sleep(1)
        except Exception:
            pass

        # 1. Click Article button to open editor
        article_btn = page.locator(page_map.COMPOSE_ARTICLE_BUTTON).first
        await article_btn.click()
        await asyncio.sleep(5)

        # 2. Fill title (textarea, NOT ProseMirror)
        title_input = page.locator(page_map.ARTICLE_TITLE).first
        await title_input.click()
        await asyncio.sleep(1)
        await title_input.fill(title)
        await asyncio.sleep(2)

        # 3. Fill body (ProseMirror inside article-editor)
        # Normalize double newlines — one Enter = new paragraph in ProseMirror
        normalized_body = re.sub(r"\n{2,}", "\n", body)
        body_editor = page.locator(page_map.ARTICLE_BODY).first
        await body_editor.click()
        await asyncio.sleep(1)
        await _type_with_hashtag_handling(page, normalized_body, delay=50)
        await asyncio.sleep(2)

        # 4. Upload cover image if provided
        if cover_path:
            try:
                logger.info(f"Uploading cover: {cover_path}")
                cover_input = page.locator(page_map.ARTICLE_COVER_INPUT).first
                await cover_input.set_input_files(cover_path)
                await asyncio.sleep(5)
            except Exception as e:
                logger.warning(f"create_article: cover upload failed: {e}")

        # 5. Insert body images if provided
        if image_paths:
            for img_path in image_paths:
                try:
                    logger.info(f"Inserting image: {img_path}")
                    img_input = page.locator(page_map.ARTICLE_IMAGE_INPUT).first
                    await img_input.set_input_files(img_path)
                    await asyncio.sleep(3)
                except Exception as e:
                    logger.warning(f"create_article: image insert failed: {e}")

        # 6. Set up response capture and publish
        post_response = None

        async def capture_post(response):
            nonlocal post_response
            if "content/add" in response.url and response.status == 200:
                try:
                    post_response = await response.json()
                except Exception:
                    pass

        page.on("response", capture_post)

        # 7. Click Publish
        publish_btn = page.locator(page_map.ARTICLE_PUBLISH_BUTTON).first
        await publish_btn.scroll_into_view_if_needed()
        await asyncio.sleep(1)
        await publish_btn.click()
        await asyncio.sleep(10)

        if post_response:
            data = post_response.get("data") or {}
            post_id = data.get("id", "")
            if post_response.get("success"):
                logger.info(f"Article published: {post_id}")
                return {"success": True, "post_id": str(post_id), "response": post_response}
            else:
                return {"success": False, "error": post_response.get("message", "Unknown"), "response": post_response}
        else:
            logger.info("Article publish clicked, no API response captured")
            return {"success": True, "post_id": "", "note": "No response captured"}

    except Exception as e:
        logger.error(f"Article creation failed: {e}")
        return {"success": False, "error": str(e)}
    finally:
        if _cleanup and pw:
            await pw.stop()


async def repost(ws_endpoint: str = None, post_id: str = "", comment: str = "", *, page=None) -> dict[str, Any]:
    """Quote-repost a post on Binance Square via browser automation.

    Flow:
    1. Navigate to post page
    2. Click quote button (div.detail-quote-button)
    3. ProseMirror editor appears inline
    4. Type comment if provided
    5. Click Post button
    """
    pw, browser, page, _cleanup = await _get_page_or_use(ws_endpoint, page=page)

    try:
        post_url = page_map.POST_URL_TEMPLATE.format(post_id=post_id)
        logger.info(f"Navigating to post: {post_url}")
        await page.goto(post_url, wait_until="domcontentloaded", timeout=60_000)
        await asyncio.sleep(5)
        await warm_up(page)

        # Dismiss cookie banner if present
        try:
            await page.locator("button#onetrust-reject-all-handler").click(timeout=3_000)
            await asyncio.sleep(1)
        except Exception:
            pass

        # Click quote button in action bar
        quote_btn = page.locator(page_map.POST_QUOTE_BUTTON).first
        await quote_btn.click()
        await asyncio.sleep(4)

        # Type comment if provided — ProseMirror editor should be visible now
        if comment:
            editor = page.locator(page_map.COMPOSE_EDITOR).first
            await editor.click(timeout=10_000)
            await asyncio.sleep(1)
            await _type_with_hashtag_handling(page, comment, delay=60)
            await asyncio.sleep(2)

        # Click Post button
        post_btn = page.locator(page_map.COMPOSE_INLINE_POST_BUTTON).first
        await post_btn.click(timeout=10_000)
        await asyncio.sleep(10)
        logger.info(f"Quote repost of {post_id} completed")
        return {"success": True, "original_post_id": post_id}

    except Exception as e:
        logger.error(f"repost: {e}, post_id={post_id}")
        return {"success": False, "error": str(e)}
    finally:
        if _cleanup and pw:
            await pw.stop()





