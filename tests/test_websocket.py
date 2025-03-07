#!/usr/bin/env python3
"""Test script for the UniFi WebSocket connection.

This script connects to a UniFi OS console and establishes a WebSocket
connection to receive real-time events. It helps diagnose connection issues.

Usage:
    python tests/test_websocket.py [--host HOSTNAME] [--username USERNAME] [--password PASSWORD]
"""

import asyncio
import argparse
import logging
import os
import sys
import json
from typing import Dict, Any
from http.cookies import SimpleCookie

import aiohttp

# Add the custom_components directory to the path so we can import modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import our custom WebSocket implementation
from custom_components.unifi_network_rules.udm.websocket import CustomUnifiWebSocket

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
LOGGER = logging.getLogger("websocket_test")

# Create handler to log to a file and console
file_handler = logging.FileHandler("websocket_test.log")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))

# Add handlers to logger
LOGGER.addHandler(file_handler)
LOGGER.addHandler(console_handler)


async def get_cookies_and_headers(
    session: aiohttp.ClientSession, host: str, username: str, password: str
) -> Dict[str, str]:
    """Authenticate to the UniFi controller and get cookies and CSRF token."""
    
    # Ensure we have a hostname without http:// prefix
    base_host = host.replace("https://", "").replace("http://", "").split(":")[0]
    base_url = f"https://{base_host}"
    
    LOGGER.info("Authenticating to UniFi controller at %s", base_url)
    
    # First, try getting a CSRF token
    try:
        csrf_token = None
        csrf_url = f"{base_url}/api/auth/csrf-token"
        async with session.get(csrf_url, ssl=False) as resp:
            if resp.status == 200:
                data = await resp.json()
                csrf_token = data.get("csrfToken")
                LOGGER.info("Retrieved CSRF token: %s", csrf_token[:5] + "..." if csrf_token else "None")
            else:
                LOGGER.warning("Failed to get CSRF token, status: %d", resp.status)
    except Exception as err:
        LOGGER.error("Error getting CSRF token: %s", err)
        csrf_token = None
    
    # Now try to login
    try:
        login_url = f"{base_url}/api/auth/login"
        headers = {}
        if csrf_token:
            headers["X-CSRF-Token"] = csrf_token
        
        login_data = {"username": username, "password": password, "rememberMe": True}
        LOGGER.info("Attempting login with username: %s", username)
        
        async with session.post(
            login_url, json=login_data, headers=headers, ssl=False
        ) as resp:
            if resp.status == 200:
                LOGGER.info("Login successful")
                
                # Get cookies from session
                cookies = session.cookie_jar.filter_cookies(login_url)
                cookie_header = "; ".join([f"{name}={cookie.value}" for name, cookie in cookies.items()])
                
                LOGGER.info("Got %d cookies", len(cookies))
                
                # Get updated CSRF token if not already present
                if not csrf_token:
                    for resp_header, value in resp.headers.items():
                        if resp_header.lower() == "x-csrf-token":
                            csrf_token = value
                            LOGGER.info("Got CSRF token from response: %s", csrf_token[:5] + "..." if csrf_token else "None")
                            break
                
                # Create headers for subsequent requests
                headers = {"Cookie": cookie_header}
                if csrf_token:
                    headers["X-CSRF-Token"] = csrf_token
                
                return headers
            else:
                LOGGER.error("Login failed with status %d: %s", resp.status, await resp.text())
                return {}
    except Exception as err:
        LOGGER.error("Error during login: %s", err)
        return {}


async def handle_websocket_message(message):
    """Handle messages from the WebSocket."""
    try:
        if isinstance(message, str):
            message_data = json.loads(message)
        else:
            message_data = message
            
        # Output message details
        msg_type = message_data.get("meta", {}).get("message", "unknown")
        LOGGER.info("Received WebSocket message: %s", msg_type)
        
        # Log rule-related messages with more detail
        rule_keywords = ["firewall", "rule", "policy"]
        if any(keyword in str(message_data).lower() for keyword in rule_keywords):
            LOGGER.info("Rule event details: %s", json.dumps(message_data, indent=2))
    except Exception as err:
        LOGGER.error("Error processing WebSocket message: %s - %s", err, message[:100] if isinstance(message, str) else str(message)[:100])


async def main(args):
    """Run the WebSocket test."""
    LOGGER.info("Starting UniFi WebSocket test")
    
    # Create session for HTTP requests
    async with aiohttp.ClientSession() as session:
        # Authenticate to get cookies and CSRF token
        headers = await get_cookies_and_headers(
            session, args.host, args.username, args.password
        )
        
        if not headers:
            LOGGER.error("Failed to get authentication headers. Exiting.")
            return
        
        # Get hostname without http:// prefix
        host = args.host.replace("https://", "").replace("http://", "").split(":")[0]
        
        # Create WebSocket client with the headers
        LOGGER.info("Creating WebSocket client for host %s", host)
        ws_client = CustomUnifiWebSocket(
            host=host,
            site=args.site,
            session=session,
            headers=headers,
            ssl=False,
        )
        
        # Set message handler
        ws_client.set_message_callback(handle_websocket_message)
        
        # Connect to the WebSocket
        LOGGER.info("Connecting to WebSocket...")
        try:
            connect_task = asyncio.create_task(ws_client.connect())
            
            # Wait for user to press Enter to exit
            LOGGER.info("WebSocket test running. Press Enter to exit.")
            
            # Create a future that will be set when Enter is pressed
            exit_future = asyncio.Future()
            
            def stdin_callback():
                """Called when input is available."""
                sys.stdin.readline()
                exit_future.set_result(None)
            
            # Add a reader for stdin
            loop = asyncio.get_event_loop()
            loop.add_reader(sys.stdin.fileno(), stdin_callback)
            
            # Wait for either the exit future to be set or 5 minutes to pass
            try:
                await asyncio.wait_for(exit_future, timeout=300)  # 5 minutes timeout
            except asyncio.TimeoutError:
                LOGGER.info("Test timeout reached (5 minutes). Exiting.")
            
            # Remove the reader
            loop.remove_reader(sys.stdin.fileno())
            
            # Close the WebSocket connection
            LOGGER.info("Closing WebSocket connection...")
            await ws_client.close()
            
            # Cancel the connect task if it's still running
            if not connect_task.done():
                connect_task.cancel()
                try:
                    await connect_task
                except asyncio.CancelledError:
                    pass
            
        except Exception as err:
            LOGGER.error("Error during WebSocket test: %s", err)
        
        LOGGER.info("WebSocket test completed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test UniFi WebSocket connection")
    parser.add_argument("--host", default="192.168.1.1", help="UniFi controller hostname or IP")
    parser.add_argument("--username", default="admin", help="UniFi controller username")
    parser.add_argument("--password", default="", help="UniFi controller password")
    parser.add_argument("--site", default="default", help="UniFi site name")
    
    args = parser.parse_args()
    
    # If password is empty, prompt for it
    if not args.password:
        import getpass
        args.password = getpass.getpass("Enter UniFi controller password: ")
    
    asyncio.run(main(args)) 