## Rules

- Always keep the code DRY for testability and separation of concerns
- Prefer modern idiomatic Python 3.13 and open source conventions, Leverage type hints, use CONST over hard coded strings
- Prioritize native Home Assistant libraries, like aiounifi, and other core capabilities to respect available resources and to avoid building duplicate fuctionality. Leverage the latest Home Assistant documentation.
- Diagnostics enabled for observability and debugging should be targeted, respecting the resources of the system
- All data retrived and stored from the API should be typed, if not supplied by aiounifi, then a custom type should be created
- When designing a new feature, prefer elegant solutions using established best practices and patterns.
- When fixing a problem or bug, avoid treating the symptop, look for the root cause.
- Details matter, ensure to always preserve existing functionlity unless otherwise instructed.
- KISS

## Notes

- If a reference to the aiounifi library is needed or required, check for a local copy in the root /aiounifi
- Changes preserving backwards compatibility may not be required, ask before assuming.
- Avoid excessive code comments
- Keep a rolling log of each change you make in a file called changelog.md

## Purpose

The focus of this home assistant custom integration is to extend the functionality of the Unifi Network application within the home assistant ecosystem. Build upon the home assistant unifi core integration and the aiounifi library. Bundling and enabling advanced automation, customizable backup and restore, and to be generally useful for homelab and home automation environments. Some examples: enhancing guest network access. Managing child device access. Promoting good security practices. This is open source and should remain accessible and usable by a wide variety of users and supported devices.
