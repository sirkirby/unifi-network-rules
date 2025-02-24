## Code notes

- Always keep the code DRY for testability and separation of concerns
- Prefer modern idiomatic Python 3.13 and open source conventions, Leverage type hints, use CONST over hard coded strings
- Prioritize native Home Assistant libraries, like aiounifi, and other core capabilities to respect available resources and to avoid building duplicate functionality.

## Integration notes

The focus of this integration is to extend the functionality of the Unifi Network application within the home assistant ecosystem. Build upon the home assistant unifi core integration and the aiounifi library. Enabling advanced automation, customizable backup and restore, and to be generally useful for homelab and home automation environments. Some examples: enhancing guest network access. Managing child device access. Promoting good security practices

## Supported features

- All UDM network and routing features are in scope