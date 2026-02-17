# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [4.4.2] - 2026-02-11

### Fixed

- Fix options flow handler crash caused by `config_entry` property conflict — the `UnifiNetworkRulesOptionsFlowHandler` constructor attempted to assign to a read-only property, raising `AttributeError` during integration configuration ([#144](https://github.com/sirkirby/unifi-network-rules/pull/144)) — [Fix component input validation and edge‑case handling in state updates](http://localhost:38567/activity/sessions/4919e801-e621-4dd2-a872-c0dae88a2de9)

> ⚠️ **Gotcha**: The options flow handler defined `config_entry` as a `@property` but the `__init__` method tried to assign to it directly. This caused a 500 error when users opened the integration's options in the UI. The fix simplifies the handler by removing the constructor entirely and relying on the base class's built-in `config_entry` access.

## [4.4.1] - 2026-01-28

### Fixed

- Improve switch toggle reliability with per-entity debouncing to prevent race conditions from rapid toggles ([#142](https://github.com/sirkirby/unifi-network-rules/pull/142))
- Add 0.5s debounce delay per switch entity — only the final desired state is submitted to the UDM API
- Resolve race conditions where concurrent toggle operations could leave switches in an inconsistent state

### Changed

- Refactor toggle operation to use `asyncio.TimerHandle` for debounce scheduling instead of immediate API calls
- Improve logging for debounced toggle operations to aid debugging

## [4.4.0] - 2025-12-29

### Fixed

- Resolve optimistic state timing issue where UI state could flash back to the previous value before the API confirmed the change ([#139](https://github.com/sirkirby/unifi-network-rules/pull/139))
- Add HA-initiated operation timeout to prevent state management race conditions between optimistic updates and coordinator refreshes

### Changed

- Code formatting and linting improvements across coordination modules
- Add CI/CD workflows for linting and testing via Makefile

## [4.3.0] - 2025-11-18

### Added

- Object Oriented Networking (OON) policy support — manage UniFi OON policies as switch entities ([#132](https://github.com/sirkirby/unifi-network-rules/pull/132))
- New [`switches/oon_policy.py`](custom_components/unifi_network_rules/switches/oon_policy.py) module with dedicated switch implementation
- New [`udm/oon.py`](custom_components/unifi_network_rules/udm/oon.py) API module for OON policy CRUD operations
- New [`models/oon_policy.py`](custom_components/unifi_network_rules/models/oon_policy.py) data model
- Test coverage for OON policy entities

## [4.2.0] - 2025-09-30

### Added

- NAT rules support — manage UniFi NAT/port translation rules as switch entities ([#125](https://github.com/sirkirby/unifi-network-rules/pull/125))
- New [`udm/nat.py`](custom_components/unifi_network_rules/udm/nat.py) API module for NAT rule operations
- New [`models/nat_rule.py`](custom_components/unifi_network_rules/models/nat_rule.py) data model
- Test coverage for NAT rule entities

### Changed

- Major refactor of coordinator into modular architecture — split monolithic coordinator into [`coordination/`](custom_components/unifi_network_rules/coordination/) subpackage with dedicated modules for auth management, data fetching, entity management, and state management
- Major refactor of switch entities into [`switches/`](custom_components/unifi_network_rules/switches/) subpackage with per-rule-type modules and a shared base class
- Improve change detection to support NAT rules and additional entity properties

## [4.1.0] - 2025-09-23

### Added

- Static routes support — manage UniFi static routes as switch entities
- New [`udm/routes.py`](custom_components/unifi_network_rules/udm/routes.py) API module for static route operations
- New [`models/static_route.py`](custom_components/unifi_network_rules/models/static_route.py) data model
- Test coverage for static route entities

### Changed

- Enhance trigger migration and template update functionality for v4.0.0 compatibility
- Simplify automation file download instructions
- Update migration utility and documentation for v4.0.0

## [4.0.0] - 2025-09-18

### Added

- Smart Polling system for efficient UDM API communication
- Unified Trigger system replacing per-rule-type triggers
- Port profile switch entities ([#100](https://github.com/sirkirby/unifi-network-rules/pull/100))
- Expanded service capabilities for rule management
- Multi-language translations (DE, ES, FR, IT, NL, PT-BR, RU)

### Changed

- Complete integration architecture overhaul
- Minimum Home Assistant version raised to 2025.8.0

---

[4.4.2]: https://github.com/sirkirby/unifi-network-rules/compare/v4.4.1...v4.4.2
[4.4.1]: https://github.com/sirkirby/unifi-network-rules/compare/v4.4.0...v4.4.1
[4.4.0]: https://github.com/sirkirby/unifi-network-rules/compare/v4.3.0...v4.4.0
[4.3.0]: https://github.com/sirkirby/unifi-network-rules/compare/v4.2.0...v4.3.0
[4.2.0]: https://github.com/sirkirby/unifi-network-rules/compare/v4.1.0...v4.2.0
[4.1.0]: https://github.com/sirkirby/unifi-network-rules/compare/v4.0.0...v4.1.0
[4.0.0]: https://github.com/sirkirby/unifi-network-rules/releases/tag/v4.0.0
