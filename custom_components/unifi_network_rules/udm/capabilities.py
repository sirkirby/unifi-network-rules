"""Module for UniFi capabilities detection."""
from ..const import LOGGER

class _Capabilities:
    """Class to detect and store UniFi device capabilities."""

    def __init__(self, api):
        """Initialize Capabilities class."""
        self._api = api
        self._legacy_firewall = None
        self._zone_based_firewall = None
        self._legacy_traffic = None

    @property
    def legacy_firewall(self) -> bool:
        """Return if legacy firewall is supported."""
        return self._legacy_firewall is True

    async def check_legacy_firewall(self) -> bool:
        """Check if the device supports legacy firewall rules."""
        try:
            rules = await self._api.get_legacy_firewall_rules()
            self._legacy_firewall = len(rules) >= 0  # Could be an empty list but still supported
            return self._legacy_firewall
        except Exception as err:
            LOGGER.debug("Legacy firewall not supported: %s", err)
            self._legacy_firewall = False
            return False

    @property
    def zone_based_firewall(self) -> bool:
        """Return if zone-based firewall is supported."""
        return self._zone_based_firewall is True

    @property
    def legacy_traffic(self) -> bool:
        """Return if legacy traffic is supported."""
        return self._legacy_traffic is True

class CapabilitiesMixin:
    """Mixin class for device capability detection."""

    @property
    def capabilities(self):
        """Get device capabilities.
        
        Returns the capabilities object, creating it if it doesn't exist.
        """
        if not hasattr(self, "_capabilities") or self._capabilities is None:
            self._capabilities = _Capabilities(self)
        return self._capabilities
    
    async def check_capabilities(self) -> None:
        """Check all device capabilities."""
        LOGGER.debug("Checking device capabilities")
        
        # Check if we have the capabilities object
        if not hasattr(self, "_capabilities") or self._capabilities is None:
            self._capabilities = _Capabilities(self)
            
        # Check legacy firewall capability
        await self.capabilities.check_legacy_firewall()
        
        LOGGER.debug("Capabilities check completed") 