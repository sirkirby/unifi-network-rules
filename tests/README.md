# UniFi Network Rules Test Scripts

This directory contains test scripts to verify the functionality of the UniFi Network Rules integration.

## WebSocket Test Script

The `test_websocket.py` script tests the WebSocket connection to a UniFi OS console. It helps diagnose issues with real-time event updates.

### Usage

```bash
python tests/test_websocket.py --host YOUR_UDM_IP --username YOUR_USERNAME
```

Or directly:

```bash
./tests/test_websocket.py --host YOUR_UDM_IP --username YOUR_USERNAME
```

The script will prompt for your password if not provided with the `--password` parameter.

### Options

- `--host`: UniFi controller hostname or IP (default: 192.168.1.1)
- `--username`: UniFi controller username (default: admin)
- `--password`: UniFi controller password (will prompt if not provided)
- `--site`: UniFi site name (default: default)

### Interpreting Results

The script will:

1. Authenticate with the UniFi controller
2. Establish a WebSocket connection
3. Print real-time events as they arrive
4. Log detailed information about rule-related events

If the script consistently fails to connect, verify:

1. Your credentials are correct
2. The UniFi OS console is reachable
3. You have the required permissions
4. There are no firewall rules blocking the WebSocket connection

### Log Files

The script creates a `websocket_test.log` file in the current directory with detailed debug information.

### Troubleshooting WebSocket Issues

This script can help diagnose the following common issues:

1. **Authentication Problems**: If you see authentication errors, check that your username and password are correct.

2. **Network Connectivity**: If the script cannot reach the UniFi controller, check your network settings and firewall rules.

3. **WebSocket URL Format**: The script tries multiple URL formats to find the one that works with your specific UniFi OS device.

4. **Session Management**: The script logs details about cookies and CSRF tokens, which can help identify session-related issues.

5. **Message Filtering**: The script logs all WebSocket messages but provides more detail for rule-related events. 