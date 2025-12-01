#!/usr/bin/env python3
"""
Test the production endpoint locally
"""
import requests
import json

def test_production_endpoint():
    """Test the production delivery endpoint"""
    
    # Test locally (when Django server is running)
    local_url = "http://localhost:8000/process-scheduled-deliveries/"
    
    print("Testing production endpoint...")
    print(f"URL: {local_url}")
    
    try:
        response = requests.post(local_url, timeout=30)
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Success: Processed {data.get('processed_announcements', 0)} announcements")
        else:
            print(f"❌ Error: {response.status_code}")
            
    except requests.exceptions.ConnectionError:
        print("❌ Connection failed. Make sure Django server is running:")
        print("   python manage.py runserver")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_production_endpoint()