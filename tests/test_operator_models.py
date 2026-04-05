"""Tests for operator models: state machine, priorities, data structures."""

from src.operator.models import (
    AgentState,
    Priority,
    AgentSlot,
    OperatorRun,
    OperatorConfig,
    validate_transition,
    VALID_TRANSITIONS,
)


class TestStateMachine:
    def test_normal_flow_transitions(self):
        path = [
            (AgentState.IDLE, AgentState.WORKING),
            (AgentState.WORKING, AgentState.COOLDOWN),
            (AgentState.COOLDOWN, AgentState.WORKING),
        ]
        for current, target in path:
            assert validate_transition(current, target), f"{current} -> {target} should be valid"

    def test_cooldown_to_idle(self):
        assert validate_transition(AgentState.COOLDOWN, AgentState.IDLE)

    def test_invalid_transition_rejected(self):
        assert not validate_transition(AgentState.IDLE, AgentState.COOLDOWN)
        assert not validate_transition(AgentState.DISABLED, AgentState.WORKING)
        assert not validate_transition(AgentState.COOLDOWN, AgentState.BLOCKED_REPLY_LIMIT)

    def test_error_transitions(self):
        assert validate_transition(AgentState.IDLE, AgentState.FAILED)
        assert validate_transition(AgentState.WORKING, AgentState.FAILED)
        assert validate_transition(AgentState.FAILED, AgentState.IDLE)
        assert validate_transition(AgentState.FAILED, AgentState.DISABLED)

    def test_adspower_down_from_working(self):
        assert validate_transition(AgentState.WORKING, AgentState.PAUSED_ADSPOWER_DOWN)

    def test_adspower_down_from_cooldown(self):
        assert validate_transition(AgentState.COOLDOWN, AgentState.PAUSED_ADSPOWER_DOWN)

    def test_paused_for_resume_from_working(self):
        assert validate_transition(AgentState.WORKING, AgentState.PAUSED_FOR_RESUME)

    def test_blocked_reply_limit_from_working(self):
        assert validate_transition(AgentState.WORKING, AgentState.BLOCKED_REPLY_LIMIT)

    def test_blocked_can_resume_working(self):
        assert validate_transition(AgentState.BLOCKED_REPLY_LIMIT, AgentState.WORKING)

    def test_all_states_have_transitions(self):
        for state in AgentState:
            assert state in VALID_TRANSITIONS, f"{state} missing from VALID_TRANSITIONS"


class TestPriority:
    def test_priority_ordering(self):
        assert Priority.RESUME_CHECKPOINT < Priority.DAILY_INCOMPLETE
        assert Priority.DAILY_INCOMPLETE < Priority.OVERFLOW
        assert Priority.OVERFLOW < Priority.BLOCKED
        assert Priority.BLOCKED < Priority.DISABLED


class TestDataStructures:
    def test_agent_slot_defaults(self):
        slot = AgentSlot(agent_id="test", config_path="test.yaml", profile_serial="1", adspower_user_id="abc")
        assert slot.state == AgentState.IDLE
        assert slot.priority == Priority.DAILY_INCOMPLETE
        assert slot.cycle_count == 0

    def test_operator_run_has_unique_id(self):
        run1 = OperatorRun(agent_id="test")
        run2 = OperatorRun(agent_id="test")
        assert run1.run_id != run2.run_id

    def test_operator_config_defaults(self):
        config = OperatorConfig()
        assert config.max_slots == 4
        assert config.prepare_timeout_sec == 300
        assert config.execute_timeout_sec == 900
        assert config.max_consecutive_errors == 3
        assert config.cycle_duration_min == (25, 40)
        assert config.cooldown_min == (10, 15)
