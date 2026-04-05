"""Browser-based data collection — feed, profiles, comments, stats.

Read-only operations that don't modify anything on Binance Square.
"""

import asyncio
import logging
import re
from typing import Any

from playwright.async_api import Page

from src.session import page_map
from src.session.browser_actions import _connect_browser, _get_page_or_use

logger = logging.getLogger("bsq.session")


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
    ws_endpoint: str = None,
    count: int = 20,
    tab: str = "recommended",
    *,
    page=None,
) -> list[dict[str, Any]]:
    """Collect posts from Binance Square feed in ONE pass from DOM.

    No navigation to individual posts — everything parsed from the feed page.
    Fast: scrolls feed, extracts post_id + author + text + likes from cards.

    Args:
        ws_endpoint: WebSocket endpoint from AdsPower
        count: Target number of posts to collect
        tab: Feed tab — "recommended" or "following"

    Returns:
        List of dicts: {post_id, author, text, like_count}
    """
    pw, browser, page, _cleanup = await _get_page_or_use(ws_endpoint, page=page)

    try:
        logger.info("Collecting feed posts...")
        await page.goto(page_map.SQUARE_URL, wait_until="domcontentloaded", timeout=60_000)
        await asyncio.sleep(5)

        # Click tab on the current Square UI (<div class="tab-item">).
        label = "Recommended" if tab == "recommended" else "Following"
        tab_selector = page_map.FEED_RECOMMENDED_TAB if tab == "recommended" else page_map.FEED_FOLLOWING_TAB
        tab_switched = False
        try:
            await page.wait_for_function('() => !!document.querySelector(".tab-item")', timeout=10_000)
            current_active = await page.evaluate(r'''(label) => {
                const items = Array.from(document.querySelectorAll('.tab-item'));
                const match = items.find(el => (el.innerText || '').trim() === label);
                return !!match && match.classList.contains('active');
            }''', label)

            if current_active:
                tab_switched = True
            else:
                try:
                    tab_el = page.locator(tab_selector).first
                    await tab_el.wait_for(state="visible", timeout=3_000)
                    await tab_el.scroll_into_view_if_needed()
                    await tab_el.click(timeout=3_000)
                    tab_switched = True
                except Exception:
                    tab_switched = await page.evaluate(r'''(label) => {
                        const items = Array.from(document.querySelectorAll('.tab-item'));
                        const match = items.find(el => (el.innerText || '').trim() === label);
                        if (!match) return false;
                        match.click();
                        return true;
                    }''', label)

            if tab_switched:
                try:
                    await page.wait_for_function(r'''(label) => {
                        const items = Array.from(document.querySelectorAll('.tab-item'));
                        const match = items.find(el => (el.innerText || '').trim() === label);
                        return !!match && match.classList.contains('active');
                    }''', label, timeout=5_000)
                except Exception:
                    await asyncio.sleep(2)
                else:
                    await asyncio.sleep(3)
        except Exception:
            tab_switched = False

        if not tab_switched:
            logger.warning(f"{tab} tab not found, using current feed")

        # Scroll to load posts
        scrolls = max(3, count // 3)
        for _ in range(scrolls):
            await page.mouse.wheel(0, 800)
            await asyncio.sleep(2)

        # Parse all posts from DOM in ONE JS pass — no navigation
        results = await page.evaluate(r'''(maxCount) => {
            const cards = document.querySelectorAll('.feed-buzz-card-base-view');
            const posts = [];
            const seen = new Set();

            for (const card of cards) {
                if (posts.length >= maxCount) break;

                // Get post_id from link
                const link = card.querySelector('a[href*="/square/post/"]');
                if (!link) continue;
                const href = link.getAttribute('href') || '';
                const match = href.match(/\/post\/(\d+)/);
                if (!match) continue;
                const postId = match[1];
                if (seen.has(postId)) continue;
                seen.add(postId);

                // Get author
                const nickEl = card.querySelector('.nick-username a.nick');
                const author = nickEl ? nickEl.textContent.trim() : 'Unknown';

                // Get text from card body
                const bodyEl = card.querySelector('.card__bd');
                const text = bodyEl ? bodyEl.innerText.trim() : '';
                if (text.length < 30) continue;

                // Get like count
                const likeEl = card.querySelector('.thumb-up-button');
                let likeCount = 0;
                if (likeEl) {
                    const likeText = likeEl.innerText.trim();
                    const num = likeText.replace(/[^0-9.kKmM]/g, '');
                    if (num.toLowerCase().includes('k')) {
                        likeCount = Math.round(parseFloat(num) * 1000);
                    } else if (num.toLowerCase().includes('m')) {
                        likeCount = Math.round(parseFloat(num) * 1000000);
                    } else {
                        likeCount = parseInt(num) || 0;
                    }
                }

                posts.push({
                    post_id: postId,
                    author: author,
                    text: text.substring(0, 1000),
                    like_count: likeCount,
                });
            }
            return posts;
        }''', count)

        logger.info(f"Collected {len(results)} posts from feed (DOM parse, no navigation)")
        return results

    except Exception as e:
        logger.error(f"Feed collection failed: {e}")
        return []
    finally:
        if _cleanup and pw:
            await pw.stop()


async def get_user_profile(ws_endpoint: str = None, username: str = "", *, page=None) -> dict[str, Any]:
    """Fetch public profile data for a Binance Square user.

    Args:
        ws_endpoint: CDP websocket endpoint
        username: Binance Square username (from profile URL)

    Returns:
        {username, name, bio, following, followers, liked, shared,
         is_following, recent_posts: [{post_id, text_preview}]}
    """
    pw, browser, page, _cleanup = await _get_page_or_use(ws_endpoint, page=page)

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
        if _cleanup and pw:
            await pw.stop()


async def get_post_comments(ws_endpoint: str = None, post_id: str = "", limit: int = 20, *, page=None) -> list[dict[str, Any]]:
    """Fetch comments on a specific post using feed-buzz-card selectors.

    Navigates to post page, scrolls to load comments, and extracts
    author + text for each comment card.

    Args:
        ws_endpoint: CDP websocket endpoint
        post_id: Post ID
        limit: Max comments to return (default 20)

    Returns:
        [{author, author_handle, text}]
    """
    pw, browser, page, _cleanup = await _get_page_or_use(ws_endpoint, page=page)

    try:
        url = page_map.POST_URL_TEMPLATE.format(post_id=post_id)
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        await asyncio.sleep(5)

        # Scroll to load comments
        for _ in range(4):
            await page.evaluate("window.scrollBy(0, 600)")
            await asyncio.sleep(2)

        comments = await page.evaluate(r'''(limit) => {
            const cards = document.querySelectorAll('.feed-buzz-card-base-view');
            const results = [];
            // Skip first card (it's the main post, not a comment)
            for (let i = 1; i < cards.length && results.length < limit; i++) {
                const card = cards[i];
                const nickEl = card.querySelector('.nick-username a.nick');
                const bodyEl = card.querySelector('.card__bd');
                if (!nickEl) continue;

                const author = nickEl.textContent.trim();
                const href = nickEl.getAttribute('href') || '';
                const handleMatch = href.match(/profile\/([^?/]+)/);
                const text = bodyEl
                    ? bodyEl.innerText.trim().substring(0, 300)
                    : '';

                results.push({
                    author: author,
                    author_handle: handleMatch ? handleMatch[1] : '',
                    text: text,
                });
            }
            return results;
        }''', limit)

        logger.info(f"get_post_comments: {len(comments)} comments on post {post_id}")
        return comments

    except Exception as e:
        logger.error(f"get_post_comments: {e}, post_id={post_id}")
        return []
    finally:
        if _cleanup and pw:
            await pw.stop()


async def get_my_comment_replies(
    ws_endpoint: str = None, username: str = "aisama", max_replies: int = 5, *, page=None
) -> list[dict[str, Any]]:
    """Find replies to agent's comments by checking the profile Replies tab.

    Rewritten flow (no back-and-forth navigation):
    1. Navigate to profile → Replies tab
    2. ONE JS pass: collect post_ids + comment text for cards with replies
    3. For each post_id, navigate directly by URL and read replies
    No returning to profile between cards.

    Args:
        ws_endpoint: CDP websocket endpoint
        username: Agent's Binance Square username
        max_replies: Maximum number of reply cards to process (default 5)

    Returns:
        [{comment_text, comment_post_id, reply_count, replies: [{author, author_handle, text}]}]
    """
    pw, browser, page, _cleanup = await _get_page_or_use(ws_endpoint, page=page)

    try:
        profile_url = f"https://www.binance.com/en/square/profile/{username}"
        await page.goto(profile_url, wait_until="domcontentloaded", timeout=60_000)
        await asyncio.sleep(5)

        # Click Replies tab
        replies_tab = page.locator("div.category:has-text('Replies')").first
        await replies_tab.click()
        await asyncio.sleep(4)

        # Scroll to load (limited)
        for _ in range(2):
            await page.evaluate("window.scrollBy(0, 700)")
            await asyncio.sleep(2)

        # ONE pass: collect post_ids from card links + comment count
        # Each reply card has a link to the post. Extract it from href.
        cards_data = await page.evaluate(r'''(username) => {
            const cards = document.querySelectorAll('.feed-buzz-card-base-view');
            const results = [];

            for (const card of cards) {
                const nickEl = card.querySelector('.nick-username a.nick');
                if (!nickEl) continue;
                const author = nickEl.textContent.trim();
                if (author !== username) continue;

                // Check comment count
                const commentIcon = card.querySelector('.comments-icon');
                const countText = commentIcon ? commentIcon.innerText.trim() : '0';
                const count = parseInt(countText) || 0;
                if (count === 0) continue;

                // Get post_id from card link
                const link = card.querySelector('a[href*="/square/post/"]');
                if (!link) continue;
                const href = link.getAttribute('href') || '';
                const match = href.match(/\/post\/(\d+)/);
                if (!match) continue;

                // Get our comment text
                const bodyEl = card.querySelector('.card__bd');
                const text = bodyEl ? bodyEl.innerText.trim().substring(0, 200) : '';

                results.push({
                    post_id: match[1],
                    comment_text: text,
                    reply_count: count,
                });
            }
            return results;
        }''', username)

        logger.info(f"get_my_comment_replies: found {len(cards_data)} comments with replies")

        if not cards_data:
            return []

        # Now visit each post directly by URL (no returning to profile)
        results = []
        for card in cards_data[:max_replies]:
            post_id = card["post_id"]
            try:
                url = page_map.POST_URL_TEMPLATE.format(post_id=post_id)
                await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                await asyncio.sleep(4)

                # Scroll to load replies
                for _ in range(2):
                    await page.evaluate("window.scrollBy(0, 500)")
                    await asyncio.sleep(1.5)

                # Read reply cards (skip first card = our comment)
                replies = await page.evaluate(r'''() => {
                    const cards = document.querySelectorAll('.feed-buzz-card-base-view');
                    const results = [];
                    for (let i = 1; i < cards.length; i++) {
                        const card = cards[i];
                        const nickEl = card.querySelector('.nick-username a.nick');
                        const bodyEl = card.querySelector('.card__bd');
                        if (!nickEl) continue;

                        const author = nickEl.textContent.trim();
                        const href = nickEl.getAttribute('href') || '';
                        const handleMatch = href.match(/profile\/([^?/]+)/);
                        const text = bodyEl
                            ? bodyEl.innerText.trim().substring(0, 300)
                            : '';

                        if (text) {
                            results.push({
                                author: author,
                                author_handle: handleMatch ? handleMatch[1] : '',
                                text: text,
                            });
                        }
                    }
                    return results;
                }''')

                results.append({
                    "comment_text": card["comment_text"],
                    "comment_post_id": post_id,
                    "reply_count": card["reply_count"],
                    "replies": replies,
                })

                logger.info(
                    f"Comment '{card['comment_text'][:40]}...' has "
                    f"{len(replies)} replies at post {post_id}"
                )

            except Exception as e:
                logger.error(f"get_my_comment_replies: error on post {post_id}: {e}")
                continue

        return results

    except Exception as e:
        logger.error(f"get_my_comment_replies: {e}")
        return []
    finally:
        if _cleanup and pw:
            await pw.stop()


async def get_post_stats(ws_endpoint: str = None, post_id: str = "", *, page=None) -> dict[str, Any]:
    """Fetch engagement stats for a specific post.

    Args:
        ws_endpoint: CDP websocket endpoint
        post_id: Post ID

    Returns:
        {post_id, likes, comments, quotes, title_preview}
    """
    pw, browser, page, _cleanup = await _get_page_or_use(ws_endpoint, page=page)

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
        if _cleanup and pw:
            await pw.stop()


async def get_my_stats(ws_endpoint: str = None, *, page=None) -> dict[str, Any]:
    """Fetch own profile stats from Creator Center.

    Returns:
        {username, handle, bio, followers, following, liked, shared,
         dashboard: {period, published, followers_gained, views, likes}}
    """
    pw, browser, page, _cleanup = await _get_page_or_use(ws_endpoint, page=page)

    try:
        await page.goto(
            page_map.CREATOR_CENTER_URL,
            wait_until="domcontentloaded",
            timeout=60_000,
        )

        try:
            await page.wait_for_function(
                r'''() => {
                    const text = document.body.innerText || '';
                    return text.includes('Creator Dashboard')
                        && text.includes('Following')
                        && text.includes('Followers')
                        && text.includes('@');
                }''',
                timeout=20_000,
            )
        except Exception:
            await asyncio.sleep(4)
        else:
            await asyncio.sleep(2)

        stats = await page.evaluate(r'''() => {
            const lines = document.body.innerText.split('\n').map(l => l.trim()).filter(Boolean);
            const result = {dashboard: {}};

            const handleIdx = lines.findIndex(l => l.startsWith('@'));
            if (handleIdx !== -1) {
                result.handle = lines[handleIdx];
                result.username = lines[handleIdx].replace('@', '');
                if (handleIdx > 0) result.name = lines[handleIdx - 1];
                const skipLabels = new Set(['Create API Key', 'Following', 'Followers', 'Liked', 'Shared']);
                for (let i = handleIdx + 1; i < Math.min(handleIdx + 6, lines.length); i++) {
                    const bioLine = lines[i];
                    if (skipLabels.has(bioLine)) continue;
                    if (bioLine.length > 10) {
                        result.bio = bioLine;
                        break;
                    }
                }
            }

            for (const label of ['Following', 'Followers', 'Liked', 'Shared']) {
                const idx = lines.findIndex(l => l === label);
                if (idx > 0) {
                    result[label.toLowerCase()] = lines[idx - 1] || '0';
                }
            }

            const dashStart = lines.findIndex(l => l === 'Creator Dashboard');
            const dashEnd = lines.findIndex(l => l === 'My Published Content');
            const dashLines = dashStart !== -1
                ? lines.slice(dashStart, dashEnd !== -1 && dashEnd > dashStart ? dashEnd : lines.length)
                : lines;

            const periodLine = dashLines.find(l => l.startsWith('Period:'));
            if (periodLine) {
                result.dashboard.period = periodLine;
            }

            const dashLabels = {
                'Published': 'published',
                'Followers gained': 'followers_gained',
                'Views': 'views',
                'Likes': 'likes',
                'Comments': 'comments',
                'Shares': 'shares',
                'Quotes': 'quotes',
                'Live Duration': 'live_duration',
            };

            for (let i = 0; i < dashLines.length; i++) {
                const key = dashLabels[dashLines[i]];
                if (!key) continue;

                let value = '';
                for (let j = i + 1; j < dashLines.length; j++) {
                    const candidate = dashLines[j];
                    if (!candidate || dashLabels[candidate] || candidate.startsWith('Period:')) continue;
                    value = candidate;
                    break;
                }

                if (value) {
                    result.dashboard[key] = value;
                }
            }

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
        if _cleanup and pw:
            await pw.stop()



