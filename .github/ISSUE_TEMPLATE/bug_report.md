---
name: Bug report
about: Create a report to help us improve
title: ''
labels: 'bug'
assignees: 'sirkirby'

---

## Debug Logging

[ ] debug logging is enabled in the configuration.

Click the "Enable Debug Logging" button in the integration configuration.

or manually add the following to your `configuration.yaml` file:

```yaml
logger:
  default: error
  logs:
    custom_components.unifi_network_rules: debug
```

Then restart Home Assistant.

## Describe the bug

A clear and concise description of what the bug is.

## To Reproduce

Steps to reproduce the behavior:

## Expected behavior

A clear and concise description of what you expected to happen.

## Screenshots

If applicable, add screenshots to help explain your problem.

## Home Assistant Logs

Paste or attach the relevant logs from the Home Assistant log file here.

## Additional context

Add any other context about the problem here.
