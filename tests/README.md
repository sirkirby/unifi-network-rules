# UniFi Network Rules Test Suite

This directory contains test scripts and unit tests to verify the functionality of the UniFi Network Rules integration.

## Unit Tests

The integration includes a suite of unit tests to verify the functionality of various components:

- `test_api.py`: Tests for the core API functionality
- `test_firewall.py`: Tests for the firewall management API
- `test_static_routes.py`: Tests for static routes functionality (models, API, switches, integration)

### Running the Unit Tests

To run the unit tests:

```bash
pytest tests/
```

To run a specific test file:

```bash
pytest tests/test_api.py
pytest tests/test_static_routes.py
```

To run with coverage report:

```bash
pytest tests/ --cov=custom_components.unifi_network_rules
```
