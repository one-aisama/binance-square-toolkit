"""Browser-based actions via Playwright CDP.

Used for operations that require client-side signature (posting, reposting)
and can't be done through pure httpx.
"""

import asyncio
import logging
import re
from typing import Any

from playwright.async_api import async_playwright, Page

from src.session import page_map

logger = logging.getLogger("bsq.session")




async def _get_page(ws_endpoint: str) -> tuple:
    """Connect to AdsPower browser and return (playwright, browser, page).

    Uses the existing first tab (context.pages[0]) so the user can see
    what's happening. Caller must stop pw when done — do NOT close the page.
    """
    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp(ws_endpoint)
    context = browser.contexts[0] if browser.contexts else await browser.new_context()
    page = context.pages[0] if context.pages else await context.new_page()
    return pw, browser, page


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
    ws_endpoint: str,
    text: str,
    coin: str | None = None,
    sentiment: str | None = None,
    image_path: str | None = None,
) -> dict[str, Any]:
    """Create a post on Binance Square via browser automation.

    Args:
        ws_endpoint: WebSocket endpoint from AdsPower
        text: Post text content (use $BTC not Bitcoin)
        coin: Optional coin ticker to attach chart (e.g. "BTC", "ETH")
        sentiment: Optional "bullish" or "bearish" to set price expectation
        image_path: Optional local file path to attach image

    Returns:
        dict with success status and any captured post data
    """
    pw, browser, page = await _get_page(ws_endpoint)

    try:
        logger.info("Navigating to Binance Square...")
        await page.goto(page_map.SQUARE_URL, wait_until="domcontentloaded", timeout=60_000)
        await asyncio.sleep(5)

        # 1. Click editor to focus
        editor = page.locator(page_map.COMPOSE_EDITOR).first
        await editor.wait_for(state="visible", timeout=15_000)
        await asyncio.sleep(1)
        await editor.click()
        await asyncio.sleep(1)

        # 2. Type text (slow, human-like) — MUST be first
        await _type_with_hashtag_handling(page, text, delay=60)
        await asyncio.sleep(2)

        # 3. Attach image if specified — BEFORE chart (order matters!)
        if image_path:
            await _attach_image_inline(page, image_path)

        # 4. Add chart if coin specified — AFTER text and image
        if coin:
            await _add_chart(page, coin)

        # 5. Set sentiment if specified
        if sentiment:
            await _set_sentiment(page, sentiment)

        # 6. Set up response capture
        post_response = None

        async def capture_post(response):
            nonlocal post_response
            if "content/add" in response.url and response.status == 200:
                try:
                    post_response = await response.json()
                except Exception:
                    pass

        page.on("response", capture_post)

        # 7. Click inline Post button
        await asyncio.sleep(2)
        post_btn = page.locator(page_map.COMPOSE_INLINE_POST_BUTTON).first
        await post_btn.wait_for(state="visible", timeout=5_000)
        await asyncio.sleep(1)
        await post_btn.click()
        await asyncio.sleep(10)

        if post_response and post_response.get("success"):
            post_id = post_response.get("data", {}).get("id", "")
            logger.info(f"Post created: {post_id}")
            return {"success": True, "post_id": str(post_id), "response": post_response}
        elif post_response:
            return {"success": False, "error": post_response.get("message", "Unknown"), "response": post_response}
        else:
            return {"success": True, "post_id": "", "note": "No response captured"}

    except Exception as e:
        logger.error(f"Post creation failed: {e}")
        return {"success": False, "error": str(e)}
    finally:
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
    ws_endpoint: str,
    title: str,
    body: str,
    cover_path: str | None = None,
    image_paths: list[str] | None = None,
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
    pw, browser, page = await _get_page(ws_endpoint)

    try:
        logger.info("Navigating to Binance Square...")
        await page.goto(page_map.SQUARE_URL, wait_until="domcontentloaded", timeout=60_000)
        await asyncio.sleep(5)

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
        await pw.stop()


async def repost(ws_endpoint: str, post_id: str, comment: str = "") -> dict[str, Any]:
    """Quote-repost a post on Binance Square via browser automation.

    Flow:
    1. Navigate to post page
    2. Click quote button (div.detail-quote-button)
    3. ProseMirror editor appears inline
    4. Type comment if provided
    5. Click Post button
    """
    pw, browser, page = await _get_page(ws_endpoint)

    try:
        post_url = page_map.POST_URL_TEMPLATE.format(post_id=post_id)
        logger.info(f"Navigating to post: {post_url}")
        await page.goto(post_url, wait_until="domcontentloaded", timeout=60_000)
        await asyncio.sleep(5)

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
        await pw.stop()


async def comment_on_post(ws_endpoint: str, post_id: str, comment_text: str) -> dict[str, Any]:
    """Comment on a post. Handles 'Follow & Reply' popup if author restricts comments to followers.

    Flow:
    1. Navigate to post
    2. Scroll to reply input (input[placeholder="Post your reply"])
    3. Type comment (delay=60ms per char)
    4. Click Reply button
    5. If "Follow & Reply" popup appears -> click it (auto-follows + sends comment)
    6. If no popup -> comment sent directly

    IMPORTANT: Do NOT write comment again after "Follow & Reply" — the original text is already sent.
    """
    pw, browser, page = await _get_page(ws_endpoint)

    try:
        post_url = page_map.POST_URL_TEMPLATE.format(post_id=post_id)
        logger.info(f"Navigating to post for comment: {post_url}")
        await page.goto(post_url, wait_until="domcontentloaded", timeout=60_000)
        await asyncio.sleep(5)

        # Scroll down to make reply input visible
        await page.evaluate("window.scrollBy(0, 800)")
        await asyncio.sleep(2)

        # Find and click reply input
        reply_input = page.locator(page_map.POST_REPLY_INPUT).first
        await reply_input.scroll_into_view_if_needed()
        await asyncio.sleep(1)
        await reply_input.click()
        await asyncio.sleep(1)

        # Type comment via keyboard (Binance custom input doesn't accept locator.type)
        await page.keyboard.type(comment_text, delay=60)
        await asyncio.sleep(2)

        # Click Reply
        reply_btn = page.locator(page_map.POST_REPLY_BUTTON).first
        await reply_btn.click()
        await asyncio.sleep(3)

        # Check if "Follow & Reply" popup appeared
        follow_reply_btn = page.locator(page_map.POST_FOLLOW_REPLY_POPUP).first
        try:
            await follow_reply_btn.wait_for(state="visible", timeout=3_000)
            # Popup appeared — click it. This auto-follows AND sends the comment.
            logger.info("Follow & Reply popup detected, clicking...")
            await follow_reply_btn.click()
            await asyncio.sleep(5)
            logger.info(f"Comment sent (via Follow & Reply) on post {post_id}")
            return {"success": True, "post_id": post_id, "followed": True}
        except Exception:
            # No popup — comment was sent directly
            await asyncio.sleep(3)
            logger.info(f"Comment sent on post {post_id}")
            return {"success": True, "post_id": post_id, "followed": False}

    except Exception as e:
        logger.error(f"Comment failed on post {post_id}: {e}")
        return {"success": False, "error": str(e)}
    finally:
        await pw.stop()


async def follow_author(ws_endpoint: str, post_id: str) -> dict[str, Any]:
    """Follow the author of a post. Checks if already following first.

    Flow:
    1. Navigate to post
    2. Find Follow button
    3. Check button text — if "Following" or "Unfollow", skip (already following)
    4. If "Follow" — click it

    IMPORTANT: If button says "Following", do NOT click — it will UNFOLLOW.
    """
    pw, browser, page = await _get_page(ws_endpoint)

    try:
        post_url = page_map.POST_URL_TEMPLATE.format(post_id=post_id)
        logger.info(f"Navigating to post for follow: {post_url}")
        await page.goto(post_url, wait_until="domcontentloaded", timeout=60_000)
        await asyncio.sleep(5)

        # Find Follow button
        follow_btn = page.locator(page_map.FOLLOW_BUTTON).first
        try:
            await follow_btn.wait_for(state="visible", timeout=5_000)
        except Exception:
            logger.info(f"No Follow button found on post {post_id} (may be own post)")
            return {"success": True, "post_id": post_id, "action": "skipped", "reason": "no_button"}

        # Check button text — "Following" means already subscribed
        btn_text = (await follow_btn.text_content() or "").strip()
        if btn_text in ("Following", "Unfollow"):
            logger.info(f"Already following author of post {post_id}")
            return {"success": True, "post_id": post_id, "action": "already_following"}

        # Safe to click — button says "Follow"
        await follow_btn.click()
        await asyncio.sleep(3)
        logger.info(f"Followed author of post {post_id}")
        return {"success": True, "post_id": post_id, "action": "followed"}

    except Exception as e:
        logger.error(f"Follow failed on post {post_id}: {e}")
        return {"success": False, "error": str(e)}
    finally:
        await pw.stop()


async def _extract_post_text(page: Page) -> str:
    """Extract clean post text from page using precise selectors.

    Uses #articleBody .richtext-container (works for both posts and articles).
    Falls back to .richtext-container if #articleBody not found.
    """
    return await page.evaluate(r'''() => {
        const container = document.querySelector('#articleBody .richtext-container')
                       || document.querySelector('.richtext-container');
        if (!container) return '';
        return container.innerText.trim();
    }''')


async def _extract_author_name(page: Page) -> str:
    """Extract author name from post page."""
    return await page.evaluate(r'''() => {
        const els = document.querySelectorAll('a[href*="/square/profile/"]');
        for (const el of els) {
            const t = (el.innerText || '').trim();
            if (t && t.length > 1 && t.length < 40) return t;
        }
        return '';
    }''')


async def collect_feed_posts(
    ws_endpoint: str,
    count: int = 20,
    tab: str = "recommended",
) -> list[dict[str, Any]]:
    """Collect posts from Binance Square feed without interacting.

    Navigates to feed, scrolls to load posts, visits each post to extract
    clean text and metadata. Returns list of posts for agent to decide on.

    Args:
        ws_endpoint: WebSocket endpoint from AdsPower
        count: Target number of posts to collect
        tab: Feed tab — "recommended" or "following"

    Returns:
        List of dicts: {post_id, author, text, like_count}
    """
    pw, browser, page = await _get_page(ws_endpoint)
    results: list[dict[str, Any]] = []

    try:
        logger.info("Collecting feed posts...")
        await page.goto(page_map.SQUARE_URL, wait_until="domcontentloaded", timeout=60_000)
        await asyncio.sleep(5)

        # Click tab
        tab_selector = page_map.FEED_RECOMMENDED_TAB if tab == "recommended" else page_map.FEED_FOLLOWING_TAB
        try:
            await page.locator(tab_selector).first.click(timeout=5_000)
            await asyncio.sleep(3)
        except Exception:
            logger.warning(f"{tab} tab not found, using default feed")

        # Scroll to load posts
        scrolls = max(3, count // 3)
        for _ in range(scrolls):
            await page.mouse.wheel(0, 800)
            await asyncio.sleep(2)

        # Collect post IDs from feed links
        post_links = await page.query_selector_all("a[href*='/square/post/']")
        post_ids: list[str] = []
        seen: set[str] = set()
        for link in post_links:
            href = await link.get_attribute("href") or ""
            parts = href.rstrip("/").split("/")
            if parts and parts[-1].isdigit():
                pid = parts[-1]
                if pid not in seen:
                    seen.add(pid)
                    post_ids.append(pid)

        logger.info(f"Found {len(post_ids)} unique posts in feed")

        # Visit each post, extract text and metadata
        for pid in post_ids:
            if len(results) >= count:
                break

            post_url = page_map.POST_URL_TEMPLATE.format(post_id=pid)
            await page.goto(post_url, wait_until="domcontentloaded", timeout=60_000)
            await asyncio.sleep(4)

            text = await _extract_post_text(page)
            author = await _extract_author_name(page)

            # Skip empty posts
            if len(text.strip()) < 30:
                continue

            # Get like count
            like_count = 0
            try:
                like_el = page.locator(page_map.POST_LIKE_BUTTON).first
                like_text = await like_el.text_content() or "0"
                like_count = int("".join(c for c in like_text if c.isdigit()) or "0")
            except Exception:
                pass

            results.append({
                "post_id": pid,
                "author": author,
                "text": text[:1000],
                "like_count": like_count,
            })
            logger.info(f"Collected post {pid} by {author} ({len(text)} chars)")

        logger.info(f"Collected {len(results)} posts total")
        return results

    except Exception as e:
        logger.error(f"Feed collection failed: {e}")
        return results
    finally:
        await pw.stop()


async def get_user_profile(ws_endpoint: str, username: str) -> dict[str, Any]:
    """Fetch public profile data for a Binance Square user.

    Args:
        ws_endpoint: CDP websocket endpoint
        username: Binance Square username (from profile URL)

    Returns:
        {username, name, bio, following, followers, liked, shared,
         is_following, recent_posts: [{post_id, text_preview}]}
    """
    pw, browser, page = await _get_page(ws_endpoint)

    try:
        url = f"https://www.binance.com/en/square/profile/{username}"
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        await asyncio.sleep(5)

        profile = await page.evaluate(r'''(username) => {
            const result = {username: username};
            const lines = document.body.innerText.split('\n').map(l => l.trim()).filter(l => l);

            // Find name — usually first substantial text or h1
            const h1 = document.querySelector('h1');
            result.name = h1 ? h1.innerText.trim() : '';

            // Parse stats by finding label positions
            const labelMap = {};
            for (let i = 0; i < lines.length; i++) {
                const l = lines[i];
                if (['Following', 'Followers', 'Liked', 'Shared', 'Posts'].includes(l)) {
                    labelMap[l] = i;
                }
            }

            // Number before "Following" = following count
            if (labelMap['Following'] !== undefined) {
                result.following = lines[labelMap['Following'] - 1] || '0';
            }

            // Number before "Followers" = followers count (line between Following and Followers)
            if (labelMap['Followers'] !== undefined) {
                result.followers = lines[labelMap['Followers'] - 1] || '0';
            }

            // Number before "Liked"
            if (labelMap['Liked'] !== undefined) {
                result.liked = lines[labelMap['Liked'] - 1] || '0';
            }

            // Number before "Shared"
            if (labelMap['Shared'] !== undefined) {
                result.shared = lines[labelMap['Shared'] - 1] || '0';
            }

            // Bio: look for description text between name area and stats
            // Usually a line with @ mention before Following count
            const followingIdx = labelMap['Following'] || 20;
            for (let i = 2; i < followingIdx - 1; i++) {
                const line = lines[i];
                if (line.startsWith('@')) {
                    result.handle = line;
                } else if (line.length > 30 && !line.startsWith('http') &&
                           line !== result.name && !line.startsWith('@')) {
                    result.bio = (result.bio || '') + line + ' ';
                }
            }
            result.bio = (result.bio || '').trim();

            // Follow button state
            const btns = document.querySelectorAll('button');
            result.is_following = false;
            for (const btn of btns) {
                const t = btn.innerText.trim();
                if (t === 'Following' || t === 'Unfollow') {
                    result.is_following = true;
                    break;
                }
            }

            // Recent post IDs
            const postLinks = document.querySelectorAll('a[href*="/square/post/"]');
            const seen = new Set();
            result.recent_posts = [];
            postLinks.forEach(a => {
                const href = a.getAttribute('href') || '';
                const parts = href.split('/');
                const id = parts[parts.length - 1];
                if (id && /^\d+$/.test(id) && !seen.has(id)) {
                    seen.add(id);
                    // Get nearby text as preview
                    const parent = a.closest('div');
                    const preview = parent ? parent.innerText.substring(0, 100).trim() : '';
                    result.recent_posts.push({post_id: id, text_preview: preview});
                }
            });

            return result;
        }''', username)

        logger.info(
            f"Profile fetched: {profile.get('name', username)}, "
            f"followers={profile.get('followers', '?')}, "
            f"posts={len(profile.get('recent_posts', []))}"
        )
        return profile

    except Exception as e:
        logger.error(f"get_user_profile: {e}, username={username}")
        return {"username": username, "error": str(e)}
    finally:
        await pw.stop()


async def get_post_stats(ws_endpoint: str, post_id: str) -> dict[str, Any]:
    """Fetch engagement stats for a specific post.

    Args:
        ws_endpoint: CDP websocket endpoint
        post_id: Post ID

    Returns:
        {post_id, likes, comments, quotes, title_preview}
    """
    pw, browser, page = await _get_page(ws_endpoint)

    try:
        url = page_map.POST_URL_TEMPLATE.format(post_id=post_id)
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        await asyncio.sleep(5)

        stats = await page.evaluate(r'''(postId) => {
            const result = {post_id: postId};

            // Like count from thumb-up-button
            const likeBtn = document.querySelector('div.thumb-up-button');
            result.likes = likeBtn ? likeBtn.innerText.trim() : '0';

            // Quote count from detail-quote-button
            const quoteBtn = document.querySelector('div.detail-quote-button');
            result.quotes = quoteBtn ? quoteBtn.innerText.trim() : '0';

            // Comment count from "Replies N" text
            const lines = document.body.innerText.split('\n').map(l => l.trim());
            for (const line of lines) {
                const match = line.match(/^Replies?\s+(\d[\d,.KkMm]*)/);
                if (match) {
                    result.comments = match[1];
                    break;
                }
            }
            if (!result.comments) result.comments = '0';

            // Title/text preview
            const content = document.querySelector('.richtext-container');
            result.title_preview = content
                ? content.innerText.trim().substring(0, 120)
                : '';

            return result;
        }''', post_id)

        logger.info(f"Post stats {post_id}: likes={stats.get('likes')}, comments={stats.get('comments')}")
        return stats

    except Exception as e:
        logger.error(f"get_post_stats: {e}, post_id={post_id}")
        return {"post_id": post_id, "error": str(e)}
    finally:
        await pw.stop()


async def get_my_stats(ws_endpoint: str) -> dict[str, Any]:
    """Fetch own profile stats from Creator Center.

    Returns:
        {username, handle, bio, followers, following, liked, shared,
         dashboard: {period, published, followers_gained, views, likes}}
    """
    pw, browser, page = await _get_page(ws_endpoint)

    try:
        await page.goto(
            page_map.CREATOR_CENTER_URL,
            wait_until="domcontentloaded",
            timeout=60_000,
        )
        await asyncio.sleep(6)

        stats = await page.evaluate(r'''() => {
            const result = {};
            const lines = document.body.innerText.split('\n').map(l => l.trim()).filter(l => l);

            // Username and handle — first lines after nav
            for (let i = 0; i < Math.min(lines.length, 20); i++) {
                if (lines[i].startsWith('@')) {
                    result.handle = lines[i];
                    result.username = lines[i].replace('@', '');
                    // Name is line before handle
                    if (i > 0) result.name = lines[i - 1];
                    // Bio is line after handle
                    // Bio: skip known UI labels
                    const skipLabels = ['Following', 'Followers', 'Create API Key',
                                        'Creator Dashboard', 'Liked', 'Shared'];
                    if (i + 1 < lines.length && lines[i + 1].length > 10
                        && !skipLabels.includes(lines[i + 1])) {
                        result.bio = lines[i + 1];
                    }
                    break;
                }
            }

            // Profile stats: Following, Followers, Liked, Shared
            const labelMap = {};
            for (let i = 0; i < lines.length; i++) {
                if (['Following', 'Followers', 'Liked', 'Shared'].includes(lines[i])) {
                    labelMap[lines[i]] = i;
                }
            }
            for (const [label, idx] of Object.entries(labelMap)) {
                result[label.toLowerCase()] = lines[idx - 1] || '0';
            }

            // Creator Dashboard stats (label on line N, value on line N+1)
            result.dashboard = {};
            const dashLabels = ['Published', 'Followers gained', 'Views', 'Likes',
                                'Comments', 'Shares', 'Quotes', 'Live Duration'];
            // Only parse dashboard section (after "Creator Dashboard" line)
            let dashStart = lines.findIndex(l => l === 'Creator Dashboard');
            let dashEnd = lines.findIndex(l => l === 'My Published Content');
            if (dashEnd === -1) dashEnd = lines.length;
            for (let i = dashStart; i < dashEnd; i++) {
                for (const label of dashLabels) {
                    if (lines[i] === label && i + 1 < dashEnd) {
                        result.dashboard[label.toLowerCase().replace(' ', '_')] = lines[i + 1];
                    }
                }
            }

            // Period
            const periodLine = lines.find(l => l.startsWith('Period:'));
            if (periodLine) result.dashboard.period = periodLine;

            return result;
        }''')

        logger.info(
            f"My stats: {stats.get('username', '?')}, "
            f"followers={stats.get('followers', '?')}"
        )
        return stats

    except Exception as e:
        logger.error(f"get_my_stats: {e}")
        return {"error": str(e)}
    finally:
        await pw.stop()
