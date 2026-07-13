#!/usr/bin/env python3
"""Check debug server status and logs."""

import requests
import json

def check_debug_server():
    """Check debug server health and logs."""
    base_url = "http://localhost:8080"
    
    try:
        # Check health
        health_response = requests.get(f"{base_url}/health", timeout=5)
        print("Health check:")
        print(json.dumps(health_response.json(), indent=2))
        
        # Get logs
        logs_response = requests.get(f"{base_url}/logs", timeout=5)
        print("\nLogs:")
        print(json.dumps(logs_response.json(), indent=2))
        
        # Get session info
        session_response = requests.get(f"{base_url}/session", timeout=5)
        print("\nSession info:")
        print(json.dumps(session_response.json(), indent=2))
        
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to debug server at localhost:8080")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_debug_server()