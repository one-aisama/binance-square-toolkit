"""Integration test for CDP harvester — requires running AdsPower."""

import pytest
from src.session.harvester import harvest_credentials


@pytest.mark.skip(reason="Requires running AdsPower with logged-in Binance profile")
async def test_harvest_real():
    """Run manually: pytest tests/test_harvester_integration.py -v --no-header -k test_harvest_real --run-skip"""
    result = await harvest_credentials("ws://127.0.0.1:XXXXX/devtools/browser/xxx")
    assert "cookies" in result
    assert "headers" in result
    assert "discovered_endpoints" in result
    assert len(result["cookies"]) > 0
    assert "csrftoken" in result["headers"] or "bnc-uuid" in result["headers"]
