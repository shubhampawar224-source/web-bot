#!/usr/bin/env python3
"""
Widget Testing Script
Tests the widget functionality and chat endpoints
"""

import sys
import os
import json
import requests
import time

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_widget_endpoints():
    """Test widget-related endpoints"""
    base_url = "http://127.0.0.1:8000"
    
    print("=" * 50)
    print("TESTING WIDGET FUNCTIONALITY")
    print("=" * 50)
    
    # Test 1: Widget HTML page
    print("\n1. Testing widget HTML endpoint...")
    try:
        response = requests.get(f"{base_url}/widget")
        if response.status_code == 200:
            print("✅ Widget HTML endpoint working")
            print(f"   Response length: {len(response.text)} characters")
        else:
            print(f"❌ Widget HTML endpoint failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Widget HTML endpoint error: {e}")
    
    # Test 2: Widget firm info endpoint
    print("\n2. Testing widget firm-info endpoint...")
    try:
        response = requests.get(f"{base_url}/widget/firm-info?urls=1,2,3&user_id=1")
        if response.status_code == 200:
            data = response.json()
            print("✅ Widget firm-info endpoint working")
            print(f"   Response: {data}")
        else:
            print(f"❌ Widget firm-info endpoint failed: {response.status_code}")
            print(f"   Response: {response.text}")
    except Exception as e:
        print(f"❌ Widget firm-info endpoint error: {e}")
    
    # Test 3: Chat endpoint
    print("\n3. Testing chat endpoint...")
    try:
        payload = {
            "query": "Hello, what can you help me with?",
            "session_id": "test_session_123",
            "firm_id": "1"
        }
        response = requests.post(
            f"{base_url}/chat",
            headers={"Content-Type": "application/json"},
            json=payload
        )
        if response.status_code == 200:
            data = response.json()
            print("✅ Chat endpoint working")
            print(f"   Answer preview: {str(data.get('answer', ''))[:100]}...")
        else:
            print(f"❌ Chat endpoint failed: {response.status_code}")
            print(f"   Response: {response.text}")
    except Exception as e:
        print(f"❌ Chat endpoint error: {e}")
    
    # Test 4: URL-specific chat endpoint
    print("\n4. Testing URL-specific chat endpoint...")
    try:
        payload = {
            "query": "Tell me about this website",
            "session_id": "test_session_456",
            "url_ids": "1,2",
            "user_id": 1,
            "firm_id": 1
        }
        response = requests.post(
            f"{base_url}/chat/url-specific",
            headers={"Content-Type": "application/json"},
            json=payload
        )
        if response.status_code == 200:
            data = response.json()
            print("✅ URL-specific chat endpoint working")
            print(f"   Answer preview: {str(data.get('answer', ''))[:100]}...")
        else:
            print(f"❌ URL-specific chat endpoint failed: {response.status_code}")
            print(f"   Response: {response.text}")
    except Exception as e:
        print(f"❌ URL-specific chat endpoint error: {e}")
    
    # Test 5: Static files
    print("\n5. Testing static files...")
    static_files = [
        "/static/index.html",
        "/static/widgets.html",
        "/static/js/script.js",
        "/static/js/widgets.js",
        "/static/css/style.css"
    ]
    
    for file_path in static_files:
        try:
            response = requests.get(f"{base_url}{file_path}")
            if response.status_code == 200:
                print(f"✅ {file_path} - OK")
            else:
                print(f"❌ {file_path} - {response.status_code}")
        except Exception as e:
            print(f"❌ {file_path} - Error: {e}")

if __name__ == "__main__":
    test_widget_endpoints()