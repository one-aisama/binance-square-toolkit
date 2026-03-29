---
globs: ["src/session/browser_actions.py", "src/session/page_map.py"]
---

# Browser Automation Rules

- All browser actions connect to AdsPower profiles via Playwright CDP — never launch bare Playwright.
- CSS selectors in `page_map.py` are fragile — Binance Square UI updates can break them at any time.
- The Square page has two Post buttons: left panel `.news-post-button` (opens a modal) and an inline publish button. Always use inline.
- Hashtag autocomplete overlaps the Post button — after each hashtag add a space or press Escape.
- The "Follow & Reply" popup must be handled when commenting — clicking it follows + submits the comment in one action. After that DO NOT write the comment again.
- `follow_author()` must check button text before clicking: "Follow" = click, "Following"/"Unfollow" = DO NOT click (it will unfollow).
- Comments on posts: DOM input `input[placeholder="Post your reply"]` + Reply button. Comments on COMMENTS: ProseMirror editor (`div.ProseMirror`) + Reply button. `comment_on_post()` automatically detects the page type.
- Like on comment page: `div.detail-thumb-up .thumb-up-button` (needs scroll_into_view — the button is often below the viewport). Like on post: `div.thumb-up-button`.
- Post creation requires a client-side nonce + signature — cannot be done via httpx, browser only.
- Spam filter in `browse_and_interact`: skip posts with text < 50 characters, likes < 3, or containing "gift", "giveaway", "airdrop", "copy trading".
- Human delay between actions: `random.uniform(15, 35) + (interacted_count * 2)` seconds.
- Always call `await pw.stop()` in the finally block after browser actions.
