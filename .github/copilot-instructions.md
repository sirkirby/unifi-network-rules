# Project Overview

This project is a custom home assistant integration to manage UniFi Network policies and rules. It is designed to provide a seamless and efficient way to manage and automate your home network policies and rules within home assistant.

## Project Structure

The project is organized into the following directories:

- `custom_components/unifi_network_rules`: The custom home assistant integration
- - `udm`: Code for interacting with the Unifi Network API
- - `models`: data models
- - `services`: custom services
- - `helpers`: helper functions
- - `utils`: utility functions
- - `manifest.json`: The manifest for the integration.
- `tests`: The test suite.
- `docs`: The documentation.

## Libraries and Frameworks

- `aiounifi`: The library for interacting with the Unifi Network API
- `homeassistant`: The library for interacting with the Home Assistant API
- python 3.13

## Coding Standards

- Always keep the code DRY for testability and separation of concerns
- Prefer modern idiomatic Python 3.13 and open source conventions, Leverage type hints, use CONST over hard coded strings
- Prioritize native Home Assistant libraries, like aiounifi, and other core capabilities to respect available resources and to avoid building duplicate functionality. Leverage the latest Home Assistant documentation.
- Diagnostics enabled for observability and debugging should be targeted, respecting the resources of the system
- All data retrieved and stored from the API should be typed, if not supplied by aiounifi, then a custom type should be created
- When designing a new feature, prefer elegant solutions using established best practices and patterns.
- When fixing a problem or bug, avoid treating the symptom, look for the root cause.
- Details matter, ensure to always preserve existing functionality unless otherwise instructed.
- KISS
