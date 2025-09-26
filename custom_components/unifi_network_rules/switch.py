"""Switch platform for UniFi Network Rules integration.

This module has been refactored into multiple modules for better organization.
All functionality is imported from the switches/ package to maintain backward compatibility.
"""
from __future__ import annotations

# Import everything from the refactored switches module for backward compatibility
from .switches import *  # noqa: F403, F401

# This ensures that existing imports like:
# from .switch import UnifiRuleSwitch
# from .switch import async_setup_entry  
# continue to work exactly as before.