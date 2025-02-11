from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.const import ATTR_ENTITY_ID
from .utils import logger
import asyncio

async def async_refresh_service(hass: HomeAssistant, call: ServiceCall) -> None:
    """Service to refresh UniFi data."""
    domain_data = hass.data.get("unifi_network_rules", {})
    tasks = []

    for entry in domain_data.values():
        coordinator = entry.get("coordinator")
        if coordinator:
            tasks.append(coordinator.async_request_refresh())
    if tasks:
        await asyncio.gather(*tasks)
        logger.debug(f"Coordinator refresh triggered via service for {len(tasks)} coordinator(s)")
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
