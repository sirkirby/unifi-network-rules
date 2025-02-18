"""Registry utilities."""
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_registry import async_get as er_async_get

if TYPE_CHECKING:
    from homeassistant.helpers.entity_registry import EntityRegistry

def async_get_registry(hass: HomeAssistant) -> "EntityRegistry":
    """Get entity registry."""
    return er_async_get(hass)