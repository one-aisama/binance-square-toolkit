"""Browser-based engagement actions via Playwright CDP.

Like, comment, follow, engage — actions that interact with existing posts.
Publishing actions (create_post, create_article, repost) live in browser_actions.py.
"""

import asyncio
import logging
from typing import Any

from playwright.async_api import Page

from src.session import page_map
from src.runtime.behavior import warm_up, mouse_move_to
from src.session.browser_actions import _connect_browser, _get_page_or_use, _detect_reply_limit

logger = logging.getLogger("bsq.session")


def _like_state_is_active(*, aria_pressed: str | None, class_name: str | None, data_state: str | None, text: str | None) -> bool:
    if str(aria_pressed or "").strip().lower() == "true":
        return True
    tokens = " ".join(str(part or "") for part in (class_name, data_state, text)).lower()
    return any(token in tokens for token in ("already liked", "active", "liked", "selected", "thumb-up-active", "unlike"))


def _like_visual_state_is_active(*, fill: str | None, color: str | None, stroke: str | None) -> bool:
    palette = " ".join(str(part or "").lower() for part in (fill, color, stroke))
    return any(
        token in palette
        for token in (
            "240, 185, 11",
            "252, 213, 53",
            "f0b90b",
            "fcd535",
            "primaryyellow",
        )
    )


async def _like_button_is_active(locator: Any) -> bool:
    try:
        aria_pressed = await locator.get_attribute("aria-pressed")
    except Exception:
        aria_pressed = None
    try:
        class_name = await locator.get_attribute("class")
    except Exception:
        class_name = None
    try:
        data_state = await locator.get_attribute("data-state")
    except Exception:
        data_state = None
    try:
        text = await locator.text_content()
    except Exception:
        text = None
    if _like_state_is_active(
        aria_pressed=aria_pressed,
        class_name=class_name,
        data_state=data_state,
        text=text,
    ):
        return True

    try:
        visual_state = await locator.evaluate(
            """(node) => {
                const target = node.querySelector('svg path') || node.querySelector('svg') || node;
                const targetStyle = window.getComputedStyle(target);
                const nodeStyle = window.getComputedStyle(node);
                return {
                    fill: targetStyle.fill,
                    stroke: targetStyle.stroke,
                    color: nodeStyle.color,
                };
            }"""
        )
    except Exception:
        visual_state = None

    if isinstance(visual_state, dict):
        return _like_visual_state_is_active(
            fill=visual_state.get("fill"),
            color=visual_state.get("color"),
            stroke=visual_state.get("stroke"),
        )
    return False


async def _resolve_like_button(page: Page) -> tuple[Any, str, str]:
    detail_like = page.locator(page_map.COMMENT_DETAIL_LIKE).first
    card_like = page.locator(page_map.POST_LIKE_BUTTON).first

    try:
        await detail_like.wait_for(state="visible", timeout=3_000)
        return detail_like, page_map.COMMENT_DETAIL_LIKE, "detail-thumb-up"
    except Exception:
        await card_like.wait_for(state="visible", timeout=10_000)
        return card_like, page_map.POST_LIKE_BUTTON, "thumb-up-button"


async def _ensure_post_liked(page: Page, post_id: str) -> dict[str, Any]:
    button, selector, label = await _resolve_like_button(page)
    await button.scroll_into_view_if_needed()
    if await _like_button_is_active(button):
        logger.info(f"Like already present on {post_id}; keeping it")
        return {"success": True, "post_id": post_id, "liked": True, "already_liked": True}

    await mouse_move_to(page, selector)
    await asyncio.sleep(1)
    await button.click()
    await asyncio.sleep(3)
    logger.info(f"Liked post {post_id} ({label})")
    return {"success": True, "post_id": post_id, "liked": True, "already_liked": False}


async def comment_on_post(
    ws_endpoint: str = None,
    post_id: str = "",
    comment_text: str = "",
    *,
    page=None,
    allow_follow_reply: bool = True,
) -> dict[str, Any]:
    """Comment on a post and only auto-follow when explicitly allowed."""
    pw, browser, page, _cleanup = await _get_page_or_use(ws_endpoint, page=page)

    try:
        post_url = page_map.POST_URL_TEMPLATE.format(post_id=post_id)
        logger.info(f"Navigating to post for comment: {post_url}")
        await page.goto(post_url, wait_until="domcontentloaded", timeout=60_000)
        await asyncio.sleep(5)
        await warm_up(page)

        await page.evaluate("window.scrollBy(0, 800)")
        await asyncio.sleep(2)

        reply_input = page.locator(page_map.POST_REPLY_INPUT).first

        try:
            await reply_input.wait_for(state="visible", timeout=3_000)
            await reply_input.scroll_into_view_if_needed()
            await asyncio.sleep(1)
            await reply_input.click()
            await asyncio.sleep(1)
        except Exception:
            logger.info("Regular reply input not found, trying ProseMirror editor (comment page)")
            editor = page.locator(page_map.COMMENT_REPLY_EDITOR).first
            await editor.scroll_into_view_if_needed()
            await asyncio.sleep(1)
            await editor.click()
            await asyncio.sleep(1)

        await page.keyboard.type(comment_text, delay=60)
        await asyncio.sleep(2)

        reply_btn = page.locator(page_map.POST_REPLY_BUTTON).first
        await mouse_move_to(page, page_map.POST_REPLY_BUTTON)
        await reply_btn.click()
        await asyncio.sleep(3)

        limit_message = await _detect_reply_limit(page)
        if limit_message:
            logger.warning(f"Reply limit exceeded on post {post_id}: {limit_message}")
            return {
                "success": False,
                "post_id": post_id,
                "error": limit_message,
                "error_code": "reply_limit_exceeded",
                "reply_limit_exceeded": True,
                "reply_limit_message": limit_message,
                "followed": False,
            }

        follow_reply_btn = page.locator(page_map.POST_FOLLOW_REPLY_POPUP).first
        try:
            await follow_reply_btn.wait_for(state="visible", timeout=3_000)
            if not allow_follow_reply:
                message = "Follow is required to reply, but follow actions are currently blocked"
                logger.warning(f"Comment blocked on post {post_id}: {message}")
                return {
                    "success": False,
                    "post_id": post_id,
                    "error": message,
                    "error_code": "follow_required",
                    "reply_requires_follow": True,
                    "followed": False,
                }
            logger.info("Follow & Reply popup detected, clicking...")
            await follow_reply_btn.click()
            await asyncio.sleep(5)

            limit_message = await _detect_reply_limit(page)
            if limit_message:
                logger.warning(f"Reply limit exceeded on post {post_id}: {limit_message}")
                return {
                    "success": False,
                    "post_id": post_id,
                    "error": limit_message,
                    "error_code": "reply_limit_exceeded",
                    "reply_limit_exceeded": True,
                    "reply_limit_message": limit_message,
                    "followed": True,
                }

            logger.info(f"Comment sent (via Follow & Reply) on post {post_id}")
            return {"success": True, "post_id": post_id, "followed": True}
        except Exception:
            await asyncio.sleep(3)
            limit_message = await _detect_reply_limit(page)
            if limit_message:
                logger.warning(f"Reply limit exceeded on post {post_id}: {limit_message}")
                return {
                    "success": False,
                    "post_id": post_id,
                    "error": limit_message,
                    "error_code": "reply_limit_exceeded",
                    "reply_limit_exceeded": True,
                    "reply_limit_message": limit_message,
                    "followed": False,
                }
            logger.info(f"Comment sent on post {post_id}")
            return {"success": True, "post_id": post_id, "followed": False}

    except Exception as e:
        logger.error(f"Comment failed on post {post_id}: {e}")
        return {"success": False, "error": str(e)}
    finally:
        if _cleanup and pw:
            await pw.stop()


async def like_post(ws_endpoint: str = None, post_id: str = "", *, page=None) -> dict[str, Any]:
    """Like a post via browser click without toggling an existing like off."""
    pw, browser, page, _cleanup = await _get_page_or_use(ws_endpoint, page=page)

    try:
        post_url = page_map.POST_URL_TEMPLATE.format(post_id=post_id)
        await page.goto(post_url, wait_until="domcontentloaded", timeout=60_000)
        await asyncio.sleep(5)
        await warm_up(page)
        return await _ensure_post_liked(page, post_id)
    except Exception as e:
        logger.error(f"Like failed on {post_id}: {e}")
        return {"success": False, "error": str(e)}
    finally:
        if _cleanup and pw:
            await pw.stop()


async def engage_post(
    ws_endpoint: str = None,
    post_id: str = "",
    like: bool = True,
    comment_text: str | None = None,
    follow: bool = False,
    *,
    page=None,
    allow_follow_reply: bool = True,
) -> dict[str, Any]:
    """Engage with a post in a single visit: like + comment + follow."""
    pw, browser, page, _cleanup = await _get_page_or_use(ws_endpoint, page=page)
    result = {
        "success": True,
        "liked": False,
        "commented": False,
        "followed": False,
        "post_id": post_id,
        "errors": [],
    }

    try:
        post_url = page_map.POST_URL_TEMPLATE.format(post_id=post_id)
        logger.info(f"Engaging with post {post_id}")
        await page.goto(post_url, wait_until="domcontentloaded", timeout=60_000)
        await asyncio.sleep(5)
        await warm_up(page)

        if like:
            try:
                like_result = await _ensure_post_liked(page, post_id)
                result["liked"] = bool(like_result.get("liked"))
                if like_result.get("already_liked"):
                    result["already_liked"] = True
                await asyncio.sleep(2)
            except Exception as e:
                result["errors"].append(f"like: {e}")
                logger.warning(f"Like failed on {post_id}: {e}")
        if comment_text:
            try:
                await page.evaluate("window.scrollBy(0, 800)")
                await asyncio.sleep(2)

                reply_input = page.locator(page_map.POST_REPLY_INPUT).first
                try:
                    await reply_input.wait_for(state="visible", timeout=3_000)
                    await reply_input.scroll_into_view_if_needed()
                    await asyncio.sleep(1)
                    await reply_input.click()
                    await asyncio.sleep(1)
                except Exception:
                    logger.info("engage_post: regular input not found, trying ProseMirror editor")
                    editor = page.locator(page_map.COMMENT_REPLY_EDITOR).first
                    await editor.scroll_into_view_if_needed()
                    await asyncio.sleep(1)
                    await editor.click()
                    await asyncio.sleep(1)
                await page.keyboard.type(comment_text, delay=60)
                await asyncio.sleep(2)

                await mouse_move_to(page, page_map.POST_REPLY_BUTTON)
                reply_btn = page.locator(page_map.POST_REPLY_BUTTON).first
                await reply_btn.click()
                await asyncio.sleep(3)

                limit_message = await _detect_reply_limit(page)
                if limit_message:
                    result["errors"].append(f"comment: {limit_message}")
                    result["error_code"] = "reply_limit_exceeded"
                    result["reply_limit_exceeded"] = True
                    result["reply_limit_message"] = limit_message
                    logger.warning(f"Reply limit exceeded on {post_id}: {limit_message}")
                else:
                    follow_reply_btn = page.locator(page_map.POST_FOLLOW_REPLY_POPUP).first
                    try:
                        await follow_reply_btn.wait_for(state="visible", timeout=3_000)
                        if not allow_follow_reply:
                            message = "Follow is required to reply, but follow actions are currently blocked"
                            result["errors"].append(f"comment: {message}")
                            result["error_code"] = "follow_required"
                            result["reply_requires_follow"] = True
                            logger.warning(f"Comment blocked on {post_id}: {message}")
                        else:
                            await follow_reply_btn.click()
                            await asyncio.sleep(5)

                            limit_message = await _detect_reply_limit(page)
                            if limit_message:
                                result["errors"].append(f"comment: {limit_message}")
                                result["error_code"] = "reply_limit_exceeded"
                                result["reply_limit_exceeded"] = True
                                result["reply_limit_message"] = limit_message
                                result["followed"] = True
                                logger.warning(f"Reply limit exceeded on {post_id}: {limit_message}")
                            else:
                                result["followed"] = True
                                logger.info(f"Comment sent via Follow & Reply on {post_id}")
                                result["commented"] = True
                    except Exception:
                        await asyncio.sleep(3)
                        limit_message = await _detect_reply_limit(page)
                        if limit_message:
                            result["errors"].append(f"comment: {limit_message}")
                            result["error_code"] = "reply_limit_exceeded"
                            result["reply_limit_exceeded"] = True
                            result["reply_limit_message"] = limit_message
                            logger.warning(f"Reply limit exceeded on {post_id}: {limit_message}")
                        else:
                            logger.info(f"Comment sent on {post_id}")
                            result["commented"] = True
            except Exception as e:
                result["errors"].append(f"comment: {e}")
                logger.warning(f"Comment failed on {post_id}: {e}")

        if follow and not result["followed"]:
            try:
                follow_btn = page.locator(page_map.FOLLOW_BUTTON).first
                btn_text = await follow_btn.text_content(timeout=3_000)
                if btn_text and "Following" not in btn_text:
                    await mouse_move_to(page, page_map.FOLLOW_BUTTON)
                    await follow_btn.click()
                    await asyncio.sleep(3)
                    result["followed"] = True
                    logger.info(f"Followed author of {post_id}")
                else:
                    logger.info(f"Already following author of {post_id}")
            except Exception as e:
                result["errors"].append(f"follow: {e}")
                logger.warning(f"Follow failed on {post_id}: {e}")

        result["success"] = len(result["errors"]) == 0
        return result

    except Exception as e:
        logger.error(f"engage_post failed on {post_id}: {e}")
        return {"success": False, "post_id": post_id, "error": str(e), "errors": [str(e)]}
    finally:
        if _cleanup and pw:
            await pw.stop()


async def follow_author(ws_endpoint: str = None, post_id: str = "", *, page=None) -> dict[str, Any]:
    """Follow the author of a post. Checks if already following first.

    IMPORTANT: If button says "Following", do NOT click — it will UNFOLLOW.
    """
    pw, browser, page, _cleanup = await _get_page_or_use(ws_endpoint, page=page)

    try:
        post_url = page_map.POST_URL_TEMPLATE.format(post_id=post_id)
        logger.info(f"Navigating to post for follow: {post_url}")
        await page.goto(post_url, wait_until="domcontentloaded", timeout=60_000)
        await asyncio.sleep(5)
        await warm_up(page)

        follow_btn = page.locator(page_map.FOLLOW_BUTTON).first
        try:
            await follow_btn.wait_for(state="visible", timeout=5_000)
        except Exception:
            logger.info(f"No Follow button found on post {post_id} (may be own post)")
            return {"success": True, "post_id": post_id, "action": "skipped", "reason": "no_button"}

        btn_text = (await follow_btn.text_content() or "").strip()
        if btn_text in ("Following", "Unfollow"):
            logger.info(f"Already following author of post {post_id}")
            return {"success": True, "post_id": post_id, "action": "already_following"}

        await mouse_move_to(page, page_map.FOLLOW_BUTTON)
        await follow_btn.click()
        await asyncio.sleep(3)
        logger.info(f"Followed author of post {post_id}")
        return {"success": True, "post_id": post_id, "action": "followed"}

    except Exception as e:
        logger.error(f"Follow failed on post {post_id}: {e}")
        return {"success": False, "error": str(e)}
    finally:
        if _cleanup and pw:
            await pw.stop()
