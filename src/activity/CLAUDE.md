# Module: activity
# Purpose: orchestration of likes, comments, reposts with human-like behavior
# Specification: docs/specs/spec_activity.md

## Files
| File | Lines | What it does |
|------|-------|------------|
| executor.py | 132 | ActivityExecutor — like/comment/repost cycle, limit checking, stub handling |
| target_selector.py | 56 | TargetSelector — post filtering, target selection by engagement |
| randomizer.py | 27 | HumanRandomizer — random delay (30-120s), probabilistic skip (35%) |
| comment_gen.py | 132 | CommentGenerator — agent tool: AI comment generation via DeepSeek/OpenAI/Anthropic |

## Dependencies
- Uses: `bapi.client` (like_post works; comment_post/repost are stubs)
- Uses: `accounts.limiter` (ActionLimiter — check and record each action)
- Used by: `scheduler` (_run_activity calls ActivityExecutor)
- Used by: `session.browser_actions` (comment_on_post, create_post via SDK)

## Key Functions
- `ActivityExecutor.run_cycle(account_id, posts, limits)` — returns `{likes, comments, reposts, skipped, errors}`
- `TargetSelector(own_account_ids, min_views=1000)` — never interacts with own accounts
- `HumanRandomizer.should_skip()` / `human_delay()` — behavior randomization
- `CommentGenerator(provider, model, api_key)` — tool for the agent, generates 1-2 sentences
- `CommentGenerator.generate(post_text, author_name)` — returns comment text

## Common Tasks
- Change delays: `HumanRandomizer(delay_range=(min, max))` in scheduler
- Change skip rate: `HumanRandomizer(skip_rate=0.35)` in scheduler
- Add action type: method in ActivityExecutor + selector in TargetSelector

## Known Issues
- comment_post and repost in BapiClient are stubs; actual actions via `session.browser_actions`
- comment_gen loads `config/content_rules.yaml`, but rules are not yet used in prompts
- Software does not generate content on its own — CommentGenerator is a tool that the agent calls
