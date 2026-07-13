#!/usr/bin/env python3
"""Test AI connection with real configuration."""

import os
import sys
import httpx

# Set debug server URL
os.environ['DEBUG_SERVER_URL'] = 'http://localhost:8080'

# Change to backend directory to load .env file
backend_dir = os.path.join(os.path.dirname(__file__), '..', 'backend')
os.chdir(backend_dir)

# Add backend to path
sys.path.insert(0, backend_dir)

from app.config import get_settings

def test_ai_connection():
    """Test AI connection with real configuration."""
    print("Testing AI connection...")
    
    try:
        # Load settings
        settings = get_settings()
        print(f"Settings loaded successfully:")
        print(f"  AI Provider: {settings.ai_provider}")
        print(f"  AI Base URL: {settings.ai_base_url}")
        print(f"  AI Chat Model: {settings.ai_chat_model}")
        print(f"  AI Embedding Model: {settings.ai_embedding_model}")
        print(f"  Has API Key: {bool(settings.ai_api_key)}")
        
        # Test AI endpoint
        print("\nTesting AI endpoint...")
        
        # Test embedding
        print("\n1. Testing embedding...")
        try:
            response = httpx.post(
                f"{settings.ai_base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {settings.ai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.ai_embedding_model,
                    "input": "Hello, this is a test.",
                },
                timeout=settings.ai_request_timeout_s,
            )
            response.raise_for_status()
            data = response.json()
            print(f"   Embedding test successful!")
            print(f"   Response status: {response.status_code}")
            print(f"   Embedding length: {len(data['data'][0]['embedding'])}")
        except Exception as e:
            print(f"   Embedding test failed: {e}")
        
        # Test chat completion
        print("\n2. Testing chat completion...")
        try:
            response = httpx.post(
                f"{settings.ai_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.ai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.ai_chat_model,
                    "messages": [
                        {"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user", "content": "Hello, how are you?"},
                    ],
                    "max_tokens": 100,
                },
                timeout=settings.ai_request_timeout_s,
            )
            response.raise_for_status()
            data = response.json()
            print(f"   Chat completion test successful!")
            print(f"   Response status: {response.status_code}")
            print(f"   Response content: {data['choices'][0]['message']['content'][:100]}...")
        except Exception as e:
            print(f"   Chat completion test failed: {e}")
        
        print("\nAI connection test completed.")
        
    except Exception as e:
        print(f"Error loading settings: {e}")
        return False
    
    return True

if __name__ == "__main__":
    success = test_ai_connection()
    sys.exit(0 if success else 1)