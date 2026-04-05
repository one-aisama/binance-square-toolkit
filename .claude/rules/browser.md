---
globs: ["src/session/browser_actions.py", "src/session/page_map.py"]
---

# Browser Automation Rules

- All browser actions connect to AdsPower profiles via Playwright CDP — never launch bare Playwright.
- CSS selectors in `page_map.py` are fragile — Binance Square UI updates can break them at any time.
- The Square page has two Post buttons: left panel `.news-post-button` (opens modal) and inline publish button. Always use inline.
- Hashtag autocomplete overlaps the Post button — add a space or press Escape after each hashtag.
- "Follow & Reply" popup must be handled during commenting — clicking it subscribes + sends comment in one action. Do NOT write the comment again after this.
- `follow_author()` must check button text before clicking: "Follow" = click, "Following"/"Unfollow" = do NOT click (would unfollow).
- Comments on posts: DOM input `input[placeholder="Post your reply"]` + Reply button. Comments on COMMENTS: ProseMirror editor (`div.ProseMirror`) + Reply button. `comment_on_post()` auto-detects page type.
- Like on comment page: `div.detail-thumb-up .thumb-up-button` (needs scroll_into_view — button is often below viewport). Like on post: `div.thumb-up-button`.
- Post creation requires client-side nonce + signature — cannot use httpx, browser only.
- Spam filter: skip posts with text < 50 chars, likes < 3, or containing "gift", "giveaway", "airdrop", "copy trading".
- Human delay between actions: `random.uniform(15, 35) + (interacted_count * 2)` seconds.
- Always call `await pw.stop()` in finally block after browser actions.
