## Current Phase: Bootstrap (Exploration)

Goal: collect data across all dimensions before optimizing. Do NOT focus on what "feels right" — systematically vary content types, target authors, and session times.

## Session Mix (mandatory)
- 1 post with image (rotate types each session: analysis → meme → hot take → news → analysis)
- 3-4 comments on different authors (vary follower ranges: <10K, 10-50K, 50K+)
- 3-5 likes (on posts you comment on + a few others)
- 1 follow (if high-value author found)

## Rules
- Never two posts of same type in a row across sessions
- Never three comments on same author in one session
- Vary session times (morning, afternoon, evening) across days
- Always check and reply to comment replies first (priority #0)
- Minimum per session: 1 post + 2 comments + 3 likes

## Exit Condition
Switch to adaptive strategy when: sample_count >= 3 for each content_type AND each author follower bracket (checked automatically by analyst.py).
