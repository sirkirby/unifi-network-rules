"""Coordination module for UniFi Network Rules integration.

This module provides coordinated data fetching, entity management, and state tracking
for the UniFi Network Rules integration. It replaces the monolithic coordinator.py
with a modular, maintainable architecture.

All exports maintain backward compatibility with existing imports.
"""

from __future__ import annotations

# Import the main coordinator class for backward compatibility
from .coordinator import UnifiRuleUpdateCoordinator

# Re-export everything that was previously available from coordinator.py
__all__ = [
    "UnifiRuleUpdateCoordinator",
]
