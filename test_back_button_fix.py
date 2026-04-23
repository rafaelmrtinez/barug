#!/usr/bin/env python3
"""
Test script to verify the back button fix for authenticated users.
This script simulates the authentication flow and checks if logged-in users
are properly redirected when trying to access the login page.
"""

import os
import sys
import django
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.sessions.models import Session

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'barug.settings')
django.setup()

def test_back_button_fix():
    """Test that authenticated users are redirected from login page"""
    client = Client()
    
    print("Testing back button fix for authenticated users...")
    
    # Test 1: Unauthenticated user should see login page
    print("\n1. Testing unauthenticated user access to login page...")
    response = client.get('/')
    print(f"   Status code: {response.status_code}")
    print(f"   Template used: {response.templates[0].name if response.templates else 'None'}")
    assert response.status_code == 200
    assert 'authentication_index.html' in [t.name for t in response.templates]
    print("   ✓ Unauthenticated users can access login page")
    
    # Test 2: Simulate authenticated user session
    print("\n2. Testing authenticated user access to login page...")
    session = client.session
    session['auth'] = {
        'staff_id': 1,
        'person_id': 1,
        'user_type': 'staff',
        'first_name': 'Test',
        'last_name': 'User',
        'role_name': 'barangay lupon president',
        'role_lower': 'barangay lupon president',
        'username': 'testuser',
        'login_at': '2024-01-01T00:00:00'
    }
    session.save()
    
    # Try to access login page while authenticated
    response = client.get('/')
    print(f"   Status code: {response.status_code}")
    print(f"   Redirect location: {response.get('Location', 'None')}")
    
    # Should be redirected (302) to dashboard
    if response.status_code == 302:
        print("   ✓ Authenticated users are redirected from login page")
        print(f"   ✓ Redirected to: {response.url}")
    else:
        print("   ✗ Authenticated users are NOT being redirected")
        return False
    
    # Test 3: Test forgot password page with authenticated user
    print("\n3. Testing authenticated user access to forgot password page...")
    response = client.get('/authentication/forgot-password/')
    print(f"   Status code: {response.status_code}")
    
    if response.status_code == 302:
        print("   ✓ Authenticated users are redirected from forgot password page")
        print(f"   ✓ Redirected to: {response.url}")
    else:
        print("   ✗ Authenticated users are NOT being redirected from forgot password page")
        return False
    
    print("\n✅ All tests passed! Back button fix is working correctly.")
    return True

def test_cache_headers():
    """Test that proper cache control headers are set"""
    client = Client()
    
    print("\n4. Testing cache control headers...")
    
    # Test login page cache headers
    response = client.get('/')
    cache_control = response.get('Cache-Control', '')
    pragma = response.get('Pragma', '')
    expires = response.get('Expires', '')
    
    print(f"   Cache-Control: {cache_control}")
    print(f"   Pragma: {pragma}")
    print(f"   Expires: {expires}")
    
    if 'no-cache' in cache_control and 'no-store' in cache_control:
        print("   ✓ Proper cache control headers are set")
        return True
    else:
        print("   ✗ Cache control headers are missing or incorrect")
        return False

if __name__ == '__main__':
    try:
        success1 = test_back_button_fix()
        success2 = test_cache_headers()
        
        if success1 and success2:
            print("\n🎉 All tests passed! The back button fix is working correctly.")
            sys.exit(0)
        else:
            print("\n❌ Some tests failed. Please check the implementation.")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)