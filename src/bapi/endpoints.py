"""Binance Square bapi endpoint constants."""

# Parsing endpoints
FEED_RECOMMEND = "/bapi/composite/v9/friendly/pgc/feed/feed-recommend/list"  # POST
TOP_ARTICLES = "/bapi/composite/v3/friendly/pgc/content/article/list"  # GET
FEAR_GREED = "/bapi/composite/v1/friendly/pgc/card/fearGreedHighestSearched"  # POST
HOT_HASHTAGS = "/bapi/composite/v2/public/pgc/hashtag/hot-list"  # GET

# Content endpoints (discovered via spike, exact usage TBD)
CONTENT_PRE_CHECK = "/bapi/composite/v1/private/pgc/content/pre-check"  # POST
CREATOR_CONTENT_LIST = "/bapi/composite/v5/private/pgc/creator/content/list"  # POST
DRAFT_COUNT = "/bapi/composite/v1/private/pgc/content/draft/count"  # POST

# User endpoints
USER_PROFILE = "/bapi/composite/v4/private/pgc/user"  # GET
SUGGESTED_CREATORS = "/bapi/composite/v1/friendly/pgc/suggested/creator/list"  # POST

# Activity endpoints (discovered via CDP network interception)
LIKE_POST = "/bapi/composite/v1/private/pgc/content/like"  # POST {"id": "<post_id>", "cardType": "BUZZ_SHORT"}
# Comment and repost endpoints — TBD (need discovery session)
