from src.session.browser_actions import (
    _normalize_compose_text,
    _post_button_state_is_enabled,
    _ui_indicates_post_success,
)
from src.session.browser_engage import (
    _like_state_is_active,
    _like_visual_state_is_active,
)


def test_like_state_detects_active_via_aria_pressed():
    assert _like_state_is_active(
        aria_pressed="true",
        class_name=None,
        data_state=None,
        text=None,
    ) is True


def test_like_state_detects_active_via_class_tokens():
    assert _like_state_is_active(
        aria_pressed=None,
        class_name="thumb-up-button active",
        data_state=None,
        text=None,
    ) is True


def test_like_state_stays_false_for_plain_button():
    assert _like_state_is_active(
        aria_pressed="false",
        class_name="thumb-up-button",
        data_state="idle",
        text="",
    ) is False


def test_like_visual_state_detects_binance_yellow_fill():
    assert _like_visual_state_is_active(
        fill="rgb(240, 185, 11)",
        color="rgb(234, 236, 239)",
        stroke="none",
    ) is True


def test_like_visual_state_stays_false_for_neutral_fill():
    assert _like_visual_state_is_active(
        fill="rgb(146, 154, 165)",
        color="rgb(234, 236, 239)",
        stroke="none",
    ) is False


def test_normalize_compose_text_collapses_whitespace():
    assert _normalize_compose_text("foo \n\n  bar\tbaz") == "foo bar baz"


def test_post_button_state_detects_disabled_button():
    assert _post_button_state_is_enabled(
        aria_disabled="true",
        disabled_attr=None,
        class_name="primary",
    ) is False
    assert _post_button_state_is_enabled(
        aria_disabled=None,
        disabled_attr="disabled",
        class_name="primary",
    ) is False
    assert _post_button_state_is_enabled(
        aria_disabled=None,
        disabled_attr=None,
        class_name="primary inactive",
    ) is False


def test_post_button_state_detects_enabled_button():
    assert _post_button_state_is_enabled(
        aria_disabled="false",
        disabled_attr=None,
        class_name="bn-button bn-button__primary",
    ) is True


def test_ui_indicates_post_success_for_post_url():
    assert _ui_indicates_post_success(
        current_url="https://www.binance.com/en/square/post/123456",
        editor_text="still there",
        original_text="still there",
        button_enabled=True,
    ) is True


def test_ui_indicates_post_success_for_cleared_compose():
    assert _ui_indicates_post_success(
        current_url="https://www.binance.com/en/square",
        editor_text="",
        original_text="the post body",
        button_enabled=False,
    ) is True


def test_ui_does_not_indicate_success_when_text_is_still_present():
    assert _ui_indicates_post_success(
        current_url="https://www.binance.com/en/square",
        editor_text="the post body with image attached",
        original_text="the post body",
        button_enabled=True,
    ) is False
