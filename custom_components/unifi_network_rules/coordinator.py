"""UniFi Network Rules Coordinator.

This module provides backward compatibility for the coordinator import.
The coordinator has been refactored into a modular architecture in the coordination/ directory.
All functionality is preserved through the new modular coordinator implementation.
"""
from __future__ import annotations

# Import the refactored coordinator for backward compatibility
from .coordination import UnifiRuleUpdateCoordinator

# Re-export the exception for backward compatibility  
class NeedsFetch(Exception):
    """Raised when a rule needs to be fetched again after a discovery."""

# Re-export everything that was previously available from this module
__all__ = [
    "UnifiRuleUpdateCoordinator", 
    "NeedsFetch",
]
