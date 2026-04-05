"""Binance Square page element selectors for Playwright CDP automation.

Discovered via DOM analysis on 2026-03-24.
"""

# ============================================================
# URLs
# ============================================================

SQUARE_URL = "https://www.binance.com/en/square"
POST_URL_TEMPLATE = "https://www.binance.com/en/square/post/{post_id}"
CREATOR_CENTER_URL = "https://www.binance.com/en/square/creator-center/home"

# ============================================================
# Inline Compose (main page feed)
# ============================================================

# Text editor (ProseMirror)
COMPOSE_EDITOR = "div.ProseMirror[contenteditable='true']"

# Publish button (inline, NOT the left-panel one)
COMPOSE_INLINE_POST_BUTTON = "button[data-bn-type='button']:not(.news-post-button):has-text('Post')"

# Left panel button (opens compose modal — DO NOT use for publishing)
COMPOSE_PANEL_BUTTON = "button.news-post-button"

# Toolbar icons (identified by stable class or position)
COMPOSE_ADD_CHART = "div.trade-widget-icon"  # Opens coin chart picker
COMPOSE_ARTICLE_BUTTON = ".article-icon"  # Opens full article editor
COMPOSE_BULLISH_ARROW = "css-pulslw"  # Green arrow — use page.locator(f'.{COMPOSE_BULLISH_ARROW}')
COMPOSE_BEARISH_ARROW = "css-1dvl0pt"  # Red arrow — use page.locator(f'.{COMPOSE_BEARISH_ARROW}')

# Hidden file input for image upload (no system dialog needed)
COMPOSE_IMAGE_INPUT = "input[type='file'][accept='.png,.jpg,.jpeg']"

# ============================================================
# Add Chart Flow
# ============================================================

# After clicking COMPOSE_ADD_CHART:
CHART_SEARCH_INPUT = "input[placeholder*='Search coin']"  # or 'Search coin or CA'
CHART_RESULT_ITEM = "text={coin}"  # Replace {coin} with e.g. "BTC"

# ============================================================
# Article Editor (full-page editor)
# ============================================================

# After clicking COMPOSE_ARTICLE_BUTTON:
ARTICLE_TITLE = "div.css-1cxhrek textarea"  # textarea inside title container
ARTICLE_BODY = ".article-editor div.ProseMirror"  # ProseMirror inside article-editor
ARTICLE_PUBLISH_BUTTON = ".article-editor-main button:has-text('Publish')"
ARTICLE_COVER_INPUT = "input[type='file'][accept='image/png, image/jpg, image/jpeg']"
ARTICLE_IMAGE_INPUT = "input[type='file'][accept='.png,.jpg,.jpeg']"

# Article toolbar (top bar with H, B, I, U, S, quote, lists, image, emoji, etc.)
# These are standard ProseMirror toolbar — use text selectors or nth-child

# ============================================================
# Post Detail Page
# ============================================================

# Post content container — use for clean text extraction (no cookie banners)
POST_CONTENT = "#articleBody .richtext-container"
POST_CONTENT_FALLBACK = ".richtext-container"

POST_LIKE_BUTTON = "div.thumb-up-button"
POST_QUOTE_BUTTON = "div.detail-quote-button div.cursor-pointer"
POST_BOOKMARK_BUTTON = "div.detail-bookmark-button"
POST_SHARE_BUTTON = "div.detail-share-button"

# Reply area on post detail page (regular input, NOT ProseMirror)
POST_REPLY_INPUT = 'input[placeholder="Post your reply"]'
POST_REPLY_BUTTON = "button:has-text('Reply')"

# Reply area on COMMENT detail page — uses ProseMirror editor, not input
# Comments (nested replies) use a different editor than top-level posts
COMMENT_REPLY_EDITOR = "div.ProseMirror"
COMMENT_DETAIL_LIKE = "div.detail-thumb-up .thumb-up-button"

# "Follow & Reply" popup — appears when author restricts comments to followers
POST_FOLLOW_REPLY_POPUP = "button:has-text('Follow & Reply')"

# Follow button — check text before clicking!
# "Follow" = not following, safe to click
# "Following" = already following, DO NOT click (will unfollow)
FOLLOW_BUTTON = "button:has-text('Follow')"

# Feed tabs
FEED_RECOMMENDED_TAB = ".tab-item:has-text('Recommended')"
FEED_FOLLOWING_TAB = ".tab-item:has-text('Following')"

