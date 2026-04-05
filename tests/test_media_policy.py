from src.runtime.media_policy import is_image_visual, recommend_visual_kind, should_attach_image


def test_media_policy_always_requires_image_for_posts():
    recent_posts = [
        {"visual_type": "chart_image"},
        {"visual_type": "chart_card"},
        {"visual_type": "text"},
    ]

    assert should_attach_image("sweetdi", recent_posts=recent_posts) is True
    assert should_attach_image("aisama", recent_posts=recent_posts) is True


def test_comments_do_not_require_image():
    assert should_attach_image("any_agent", action_type="comment") is False


def test_quote_reposts_do_not_require_image():
    assert should_attach_image("any_agent", action_type="quote_repost") is False


def test_default_action_type_is_post():
    assert should_attach_image("any_agent") is True


def test_is_image_visual_understands_generated_visual_kinds():
    assert is_image_visual("chart_capture") is True
    assert is_image_visual("news_card") is True
    assert is_image_visual("reaction_card") is True
    assert is_image_visual("editorial_card") is True
    assert is_image_visual("text") is False
    assert is_image_visual(None) is False
    assert is_image_visual("") is False


def test_recommend_market_always_chart():
    assert recommend_visual_kind("market_chart") == "chart_capture"
    assert recommend_visual_kind("market_chart", has_price_data=True, has_coin=True) == "chart_capture"


def test_recommend_news_with_price_and_coin_uses_chart():
    assert recommend_visual_kind("news_reaction", has_price_data=True, has_coin=True) == "chart_capture"


def test_recommend_news_without_price_uses_card():
    assert recommend_visual_kind("news_reaction") == "news_card"
    assert recommend_visual_kind("news_reaction", has_price_data=True, has_coin=False) == "news_card"


def test_recommend_coin_without_price_uses_editorial_card():
    assert recommend_visual_kind("editorial_note", has_coin=True) == "editorial_card"


def test_recommend_coin_with_price_uses_chart():
    assert recommend_visual_kind("editorial_note", has_coin=True, has_price_data=True) == "chart_capture"


def test_recommend_editorial_fallback_uses_reaction_card():
    assert recommend_visual_kind("editorial_note") == "reaction_card"
