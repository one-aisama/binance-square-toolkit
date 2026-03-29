from src.runtime.agent_config import load_active_agent


def test_load_active_agent():
    agent = load_active_agent('config/active_agent.yaml')
    assert agent.agent_id == 'aisama'
    assert agent.binance_username == 'aisama'
    assert agent.profile_serial == '1'
    assert agent.adspower_user_id == 'your-adspower-profile-id'
    assert agent.primary_feed_tab == 'recommended'
