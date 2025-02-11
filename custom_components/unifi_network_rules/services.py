from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.const import ATTR_ENTITY_ID
from .utils import logger

async def async_refresh_service(hass: HomeAssistant, call: ServiceCall) -> None:
    """Service to refresh UniFi data."""
    domain_data = hass.data.get("unifi_network_rules", {})
    coordinator = None

    for entry in domain_data.values():
        coordinator = entry.get("coordinator")
        break
    if coordinator:
        await coordinator.async_request_refresh()
        logger.debug("Coordinator refresh triggered via service")
    else:
        logger.debug("Coordinator not found during service call")

async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for the UniFi Network Rules integration."""
    hass.services.async_register(
        "unifi_network_rules",
        "refresh",
        async_refresh_service,
        schema=None,
    )
