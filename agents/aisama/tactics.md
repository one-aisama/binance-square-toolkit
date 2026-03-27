# Tactics — What Works on Binance Square

## Follower Growth
- **Shitposts drive subscriptions.** Relatable, funny, viral-format posts get shared and attract followers faster than pure analysis.
- **Comment on top influencers.** Find creators with large audiences (100K+ followers). Write smart, engaging comments on their posts. Their audience sees your comment → visits your profile → follows if content is good.
- **Hook the influencer.** If your comment is good enough, the influencer follows you back — massive signal boost.
- **Consistency beats volume.** Better 2 great posts/day than 10 mediocre ones.

## Engagement
- **Reply to replies.** When someone comments on your post, reply back. Builds community.
- **Quote repost with take.** Don't just repost — add your own angle. Shows you think.
- **Timing matters.** Post when market is moving (high volatility = high attention).
- **Use $CASHTAGS always.** Posts with $BTC, $ETH appear in coin-specific feeds → more exposure. Also drives Write to Earn commissions when readers click and trade.
- **Images boost everything.** Posts with images get more views, more engagement, more shares. Always attach something — chart screenshot, meme, relevant visual. A text-only post is a missed opportunity.

## Binance Square Platform Rules (from Creator Academy)
- **Avatar + nickname = mandatory.** Algorithm reduces reach for profiles without them.
- **$CASHTAGS feed visibility.** When you write $BTC, your post appears in the BTC-specific feed. More tags = more feeds = more eyeballs.
- **Hashtags must be relevant.** Irrelevant hashtag spam = platform violation. Only use tags that match your content.
- **No links to Telegram/Discord/external platforms.** Instant violation.
- **No giveaways, no begging, no "comment UID" style posts.**
- **No copying other creators' content.** Must be original or clearly add your own perspective.
- **Write to Earn:** readers who click $CASHTAGS and trade → you earn 20-50% commission. This is real money — but only matters once you have an audience reading your posts.
- **Content "lives" for 7 days** for earning purposes. After that, no more commission from that post.

## Content that performs
- Market dumps → memes, relatable humor, "we've been here before"
- Breakouts → quick analysis with chart screenshot, levels to watch
- News → fast hot take before everyone else posts the same headline
- Educational → "here's what RSI actually tells you" type explainers
- Controversial → unpopular opinions backed by data get engagement

## What to avoid
- Generic "BTC is pumping!" posts with no substance
- Copying other creators' takes word for word
- Begging for likes/follows
- Posting too frequently (looks like a bot)
- Mechanical trade calls without context ("BUY NOW RSI OVERSOLD")

## Metrics to track
- Followers gained per day
- Views per post
- Like-to-view ratio
- Which post types get most engagement
- Which influencers' audiences convert best

## Session learnings

### Session 1 (2026-03-27)
- **Browser cold start can cause post creation to fail.** First attempt timed out on ProseMirror selector, retry worked. If first post fails, retry once before giving up.
- **Red market days = high engagement potential.** People scroll more when anxious. Good time for both analysis and relatable commentary.
- **Feed has lots of spam to filter.** Posts under 50 chars, "click here to trade", giveaway spam — skip these. Look for substantive posts with 15+ likes.
- **Dollar signs in post text need escaping in Python strings.** Use `\$BTC` in f-strings or raw strings to avoid issues.
- **Comments on mid-popularity posts (15-30 likes) go through cleanly.** No Follow & Reply popup encountered. Good sweet spot for visibility without gatekeeping.

### Session 2 (2026-03-28)
- **New accounts need comments more than posts.** Session 1 posts got 0 engagement with 0 followers. Posts are invisible without distribution. Comments on popular posts (50-150 likes) are the real growth engine — people see your comment, visit profile, follow.
- **Always attach images to posts.** Chart screenshots for analysis, memes for commentary. The ETH 4H chart and "this is fine" meme both worked seamlessly. `sdk.screenshot_chart()` and `sdk.download_image()` are reliable.
- **Feed is polluted with campaign spam.** SIGN token promo and generic Web3 identity posts flood recommended feed. Skip these — look for real market discussion posts.
- **Data-backed contrarian comments stand out.** Instead of "I'd buy SOL!" on a "$20K which coin" post, dropping real TA data (MACD bearish cross, 42% below MA200) with a "wait for bottom" take is memorable and differentiated.
- **Consecutive red days = good content opportunity.** Day 2 of bleeding lets you reference trends ("second day testing support") rather than reacting to a single move. More analytical credibility.
- **Meme downloads work for mood posts.** imgflip URLs work with `sdk.download_image()`. Good source for relatable market memes.
