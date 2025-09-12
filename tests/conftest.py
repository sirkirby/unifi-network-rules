import pytest
from homeassistant.core import HomeAssistant

@pytest.fixture
async def hass(event_loop):
    """Fixture to provide a test instance of Home Assistant."""
    hass = HomeAssistant(config_dir="/tmp")
    hass.config.components.add("unifi_network_rules")
    yield hass
    await hass.async_stop()