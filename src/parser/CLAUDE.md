# Module: parser
# Purpose: fetching posts from bapi, parsing raw responses, ranking trends by engagement
# Specification: docs/specs/spec_parser.md

## Files
| File | Lines | What it does |
|------|-------|------------|
| fetcher.py | 114 | TrendFetcher — loading articles + feed via BapiClient, deduplication by post_id |
| aggregator.py | 59 | rank_topics() — grouping by hashtag, scoring: views*0.3 + likes*0.5 + comments*0.2 |
| models.py | 32 | ParsedPost and Topic dataclasses |

## Dependencies
- Uses: `bapi.client` (BapiClient — all data flows through it)
- Used by: `content` (topics are fed to ContentGenerator)
- Used by: `activity` (posts are used as targets)
- Used by: `scheduler` (calls TrendFetcher.fetch_all + rank_topics)

## Key Functions
- `TrendFetcher(client: BapiClient)` — constructor
- `TrendFetcher.fetch_all(article_pages=5, feed_pages=5)` — returns `list[ParsedPost]`
- `TrendFetcher.fetch_fear_greed()` — returns dict
- `TrendFetcher.fetch_hot_hashtags()` — returns list of dicts
- `rank_topics(posts, top_n=10)` — returns `list[Topic]`
- `compute_engagement(post)` — returns float score

## Common Tasks
- Change ranking formula: `compute_engagement()` in `aggregator.py`
- Fix bapi parsing: `_extract_post()` in `fetcher.py` — handles nested `contentDetail`
- Add data source: add method to TrendFetcher, call in `fetch_all()`

## Known Issues
- Bapi response structure differs between feed and article endpoints — `_extract_post()` tries multiple paths
- Posts without hashtags (`_untagged`) are excluded from topic ranking
