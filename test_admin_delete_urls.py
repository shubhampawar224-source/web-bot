#!/usr/bin/env python3
"""
Test script for admin URL deletion functionality
"""

import requests
import json

# Test admin login and URL deletion
BASE_URL = "http://127.0.0.1:8000"

def test_admin_login():
    """Test admin login and get token"""
    print("🔐 Testing admin login...")
    
    response = requests.post(f"{BASE_URL}/admin/login", json={
        "username": "admin",
        "password": "admin123"
    })
    
    if response.status_code == 200:
        data = response.json()
        if data.get("status") == "success":
            print("✅ Admin login successful")
            return data.get("token")
        else:
            print(f"❌ Login failed: {data.get('message')}")
            return None
    else:
        print(f"❌ Login request failed: {response.status_code}")
        return None

def test_get_urls(token):
    """Get list of URLs"""
    print("📋 Getting URL list...")
    
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{BASE_URL}/admin/all-urls", headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        if data.get("status") == "success":
            urls = data.get("urls", [])
            print(f"✅ Found {len(urls)} URLs")
            for i, url in enumerate(urls[:3]):  # Show first 3
                print(f"  {i+1}. ID: {url.get('id')}, URL: {url.get('url')}")
            return urls
        else:
            print(f"❌ Failed to get URLs: {data.get('message')}")
    else:
        print(f"❌ Get URLs request failed: {response.status_code}")
    
    return []

def test_delete_url(token, url_id):
    """Test deleting a specific URL"""
    print(f"🗑️ Testing delete URL with ID: {url_id}")
    
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.delete(f"{BASE_URL}/admin/delete-url/{url_id}", headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        if data.get("status") == "success":
            print(f"✅ URL deleted successfully: {data.get('message')}")
            return True
        else:
            print(f"❌ Delete failed: {data.get('message')}")
    else:
        print(f"❌ Delete request failed: {response.status_code}")
        try:
            error_data = response.json()
            print(f"Error details: {error_data}")
        except:
            print(f"Response text: {response.text}")
    
    return False

def test_bulk_delete_urls(token, url_ids):
    """Test bulk deleting URLs"""
    print(f"🗑️ Testing bulk delete for {len(url_ids)} URLs")
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {"url_ids": url_ids}
    
    response = requests.post(f"{BASE_URL}/admin/bulk-delete-urls", 
                           headers=headers, 
                           json=payload)
    
    if response.status_code == 200:
        data = response.json()
        if data.get("status") == "success":
            print(f"✅ Bulk delete successful: {data.get('message')}")
            return True
        else:
            print(f"❌ Bulk delete failed: {data.get('message')}")
    else:
        print(f"❌ Bulk delete request failed: {response.status_code}")
        try:
            error_data = response.json()
            print(f"Error details: {error_data}")
        except:
            print(f"Response text: {response.text}")
    
    return False

def main():
    print("🧪 Starting Admin URL Deletion Tests")
    print("=" * 50)
    
    # Test login
    token = test_admin_login()
    if not token:
        print("❌ Cannot proceed without admin token")
        return
    
    print("\n" + "=" * 50)
    
    # Get URLs
    urls = test_get_urls(token)
    if not urls:
        print("ℹ️ No URLs to test deletion")
        return
    
    print("\n" + "=" * 50)
    print("🔍 Available endpoints for testing:")
    print(f"- DELETE {BASE_URL}/admin/delete-url/{{url_id}}")
    print(f"- POST {BASE_URL}/admin/bulk-delete-urls")
    print("\n⚠️ Run this script manually to avoid accidentally deleting data")
    print("Example usage:")
    print(f"  test_delete_url('{token}', {urls[0].get('id') if urls else 'URL_ID'})")
    
    # Uncomment to actually test deletion (be careful!)
    # if len(urls) > 0:
    #     test_delete_url(token, urls[0]['id'])

if __name__ == "__main__":
    main()