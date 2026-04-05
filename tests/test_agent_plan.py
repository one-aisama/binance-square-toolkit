import json

import pytest

from src.runtime.agent_plan import load_agent_plan


def test_agent_plan_requires_text_for_quote_repost(tmp_path):
    plan_path = tmp_path / 'invalid_plan.json'
    plan_path.write_text(
        json.dumps(
            [
                {
                    'action': 'quote_repost',
                    'target': '123456',
                    'priority': 1,
                    'reason': 'quote a visible thread',
                }
            ]
        ),
        encoding='utf-8',
    )

    with pytest.raises(ValueError):
        load_agent_plan(str(plan_path))


def test_agent_plan_allows_comment_without_text(tmp_path):
    """Comment text is written by the agent later, not at plan time."""
    plan_path = tmp_path / 'valid_comment_plan.json'
    plan_path.write_text(
        json.dumps(
            [
                {
                    'action': 'comment',
                    'target': '123456',
                    'priority': 1,
                    'reason': 'reply to a visible thread',
                    'target_text': 'original post text',
                }
            ]
        ),
        encoding='utf-8',
    )

    plan = load_agent_plan(str(plan_path))
    assert plan.actions[0].text is None
    assert plan.actions[0].target_text == 'original post text'


def test_agent_plan_accepts_explicit_agent_text(tmp_path):
    plan_path = tmp_path / 'valid_plan.json'
    plan_path.write_text(
        json.dumps(
            {
                'actions': [
                    {
                        'action': 'comment',
                        'target': '123456',
                        'target_author': 'macrocat',
                        'priority': 1,
                        'reason': 'answer a market thread',
                        'text': 'i get the thesis but that level already got tested too many times',
                        'like': True,
                    },
                    {
                        'action': 'post',
                        'priority': 2,
                        'reason': 'publish market take',
                        'text': '$BTC still looks rangebound to me\n\n#Bitcoin #CryptoMarket',
                        'coin': 'BTC',
                        'chart_symbol': 'BTC_USDT',
                    },
                ]
            }
        ),
        encoding='utf-8',
    )

    plan = load_agent_plan(str(plan_path))

    assert len(plan.actions) == 2
    assert plan.actions[0].action == 'comment'
    assert plan.actions[0].like is True
    assert plan.actions[1].chart_symbol == 'BTC_USDT'
    assert plan.actions[1].chart_image is False


def test_agent_plan_rejects_mixed_chart_card_and_chart_image(tmp_path):
    plan_path = tmp_path / 'invalid_mixed_media_plan.json'
    plan_path.write_text(
        json.dumps(
            {
                'actions': [
                    {
                        'action': 'post',
                        'priority': 1,
                        'reason': 'market take',
                        'text': '$BTC still looks reactive here\n\n#BTC #Bitcoin',
                        'coin': 'BTC',
                        'chart_symbol': 'BTC_USDT',
                        'chart_image': True,
                    }
                ]
            }
        ),
        encoding='utf-8',
    )

    with pytest.raises(ValueError):
        load_agent_plan(str(plan_path))


def test_agent_plan_requires_chart_symbol_when_chart_image_enabled(tmp_path):
    plan_path = tmp_path / 'invalid_chart_image_plan.json'
    plan_path.write_text(
        json.dumps(
            {
                'actions': [
                    {
                        'action': 'post',
                        'priority': 1,
                        'reason': 'market take',
                        'text': '$BTC still looks reactive here\n\n#BTC #Bitcoin',
                        'chart_image': True,
                    }
                ]
            }
        ),
        encoding='utf-8',
    )

    with pytest.raises(ValueError):
        load_agent_plan(str(plan_path))


def test_agent_plan_requires_capture_url_for_capture_rules(tmp_path):
    plan_path = tmp_path / 'invalid_capture_plan.json'
    plan_path.write_text(
        json.dumps(
            {
                'actions': [
                    {
                        'action': 'post',
                        'priority': 1,
                        'reason': 'capture page fragment',
                        'text': 'headline flow matters less than the second move\n\nthat is where the tape stops borrowing conviction',
                        'visual_kind': 'page_capture',
                        'capture_selectors': ['.headline'],
                    }
                ]
            }
        ),
        encoding='utf-8',
    )

    with pytest.raises(ValueError):
        load_agent_plan(str(plan_path))
