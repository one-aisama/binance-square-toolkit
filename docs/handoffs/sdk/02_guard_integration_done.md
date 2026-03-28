# Guard Integration: SDK

## What was done
ActionGuard integrated into BinanceSquareSDK as an optional parameter.
Every action method now checks guard before executing and records result after.

## Changes
- `src/sdk.py` -- constructor accepts `guard: ActionGuard | None`, added `_check_guard()` and `_record_guard()` helpers, wrapped all 6 action methods
- `tests/test_sdk.py` -- added 15 guard integration tests

## Action methods wrapped
- `create_post` -- guard type: "post"
- `create_article` -- guard type: "post" (shares limit with create_post)
- `comment_on_post` -- guard type: "comment"
- `like_post` -- guard type: "like"
- `quote_repost` -- guard type: "quote_repost"
- `follow_user` -- guard type: "follow"

## Guard behavior
- Guard is optional (None by default) -- existing code without guard works unchanged
- When guard denies: returns `{"success": False, "error": "Guard denied: <type>"}`
- When guard says WAIT: SDK sleeps the requested duration, then re-checks
- When guard says SESSION_OVER: returns denied response
- On success/failure: `guard.record()` is called with action type and result

## Implemented tests
- test_constructor_guard_is_none_by_default -- guard defaults to None
- test_constructor_accepts_guard -- guard is stored correctly
- test_check_guard_allows_when_no_guard -- no guard = always allow
- test_check_guard_allows_when_verdict_allow -- ALLOW verdict passes
- test_check_guard_denies_when_verdict_denied -- DENIED verdict blocks
- test_check_guard_denies_when_session_over -- SESSION_OVER blocks
- test_like_post_denied_by_guard -- like returns error dict
- test_comment_denied_by_guard -- comment returns error dict
- test_create_post_denied_by_guard -- post returns error dict
- test_create_article_denied_by_guard -- article returns error dict
- test_quote_repost_denied_by_guard -- repost returns error dict
- test_follow_user_denied_by_guard -- follow returns error dict
- test_comment_records_success_in_guard -- guard.record called on success
- test_follow_records_success_in_guard -- guard.record called on success
- test_record_guard_noop_without_guard -- no crash when guard is None

## Business logic notes for frontend-developer
- Guard check happens BEFORE validation -- if guard denies, validation is skipped
- Data methods (get_feed_posts, get_market_data, etc.) are NOT guarded
- create_article shares the "post" action type with create_post for limit purposes

## Known limitations
- WAIT verdict does a single retry after sleeping -- if still denied after wait, action is blocked (no loop)
