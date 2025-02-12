import pytest
from unittest.mock import Mock, patch
from homeassistant.core import HomeAssistant
import asyncio
import warnings

@pytest.fixture
async def hass(event_loop):
    """Fixture to provide a test instance of Home Assistant."""
    hass = HomeAssistant(config_dir="/tmp")
    hass.config.components.add("unifi_network_rules")
    yield hass
    await hass.async_stop()

@pytest.fixture
async def mock_udmapi():
    """Fixture to provide a mocked UDMAPI instance."""
    with patch('custom_components.unifi_network_rules.udm_api.UDMAPI') as mock_api:
        api = mock_api.return_value
        api.login.return_value = (True, None)
        api.get_traffic_rules.return_value = (True, [{"_id": "1", "enabled": True, "description": "Test Traffic Rule"}], None)
        api.get_firewall_rules.return_value = (True, [{"_id": "2", "enabled": False, "description": "Test Firewall Rule"}], None)
        yield api

@pytest.fixture
async def mock_config_entry():
    """Fixture to provide a mocked config entry."""
    return Mock(
        data={
            "host": "192.168.1.1",
            "username": "admin",
            "password": "password",
            "max_retries": 3,
            "retry_delay": 1
        },
        entry_id="test_entry_id"
    )

def pytest_configure(config):
    """Configure pytest."""
    # Filter out specific deprecation warnings from dependencies
    warnings.filterwarnings(
        "ignore",
        category=DeprecationWarning,
        module="josepy.util"
    )
    warnings.filterwarnings(
        "ignore",
        category=DeprecationWarning,
        module="acme.crypto_util"
    )
    # Filter Home Assistant web application warning
    warnings.filterwarnings(
        "ignore",
        category=DeprecationWarning,
        message="Inheritance class HomeAssistantApplication from web.Application is discouraged"
    )
    # Filter RuntimeWarning for unawaited coroutines in tests
    warnings.filterwarnings(
        "ignore",
        category=RuntimeWarning,
        message="coroutine '.*' was never awaited"
    )