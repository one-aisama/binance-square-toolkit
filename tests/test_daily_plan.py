from datetime import datetime, timezone

from src.runtime.daily_plan import (
    count_daily_results,
    is_daily_plan_complete,
    load_daily_plan_state,
    remaining_daily_targets,
    update_daily_plan_state,
)


def test_daily_plan_resets_when_local_day_changes(tmp_path):
    path = tmp_path / 'daily_plan.json'
    targets = {'like': 4, 'comment': 2, 'post': 1}

    first_state = load_daily_plan_state(
        'sweetdi',
        targets=targets,
        timezone_name='UTC',
        current_time=datetime(2026, 3, 30, 8, 0, tzinfo=timezone.utc),
        path=path,
    )
    update_daily_plan_state(
        'sweetdi',
        [{'action': 'like', 'success': True, 'response': {'success': True}}],
        targets=targets,
        timezone_name='UTC',
        current_time=datetime(2026, 3, 30, 9, 0, tzinfo=timezone.utc),
        path=path,
    )
    second_state = load_daily_plan_state(
        'sweetdi',
        targets=targets,
        timezone_name='UTC',
        current_time=datetime(2026, 3, 31, 8, 0, tzinfo=timezone.utc),
        path=path,
    )

    assert first_state['plan_date'] != second_state['plan_date']
    assert second_state['completed']['like'] == 0
    assert second_state['status'] == 'in_progress'


def test_daily_plan_marks_completion_and_remaining_targets(tmp_path):
    path = tmp_path / 'daily_plan.json'
    targets = {'like': 2, 'comment': 1, 'post': 1}

    state = update_daily_plan_state(
        'aisama',
        [
            {'action': 'like', 'success': True, 'response': {'success': True}},
            {'action': 'comment', 'success': True, 'response': {'commented': True, 'liked': True}},
            {'action': 'post', 'success': True, 'response': {'success': True}},
        ],
        targets=targets,
        timezone_name='UTC',
        current_time=datetime(2026, 3, 30, 10, 0, tzinfo=timezone.utc),
        path=path,
    )

    assert is_daily_plan_complete(state) is True
    assert remaining_daily_targets(state) == {'like': 0, 'comment': 0, 'post': 0}
    assert state['status'] == 'completed'


def test_count_daily_results_handles_combined_comment_actions():
    counts = count_daily_results(
        [
            {'action': 'comment', 'success': True, 'response': {'commented': True, 'liked': True, 'followed': True}},
            {'action': 'comment', 'success': True, 'response': {'reply_limit_exceeded': True, 'liked': True}},
        ]
    )

    assert counts['comment'] == 1
    assert counts['like'] == 2
    assert counts['follow'] == 1
