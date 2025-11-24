#!/usr/bin/env python
"""
Test script for audience backend functionality
"""
import os
import sys
import django
from django.conf import settings

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'barug.settings')
django.setup()

from src.app.transfer_objects.commands.audience_cmd import AddAnnouncementAudienceCMD
from src.app.transfer_objects.commands.announcement_cmd import CreateAnnouncementDraftCMD
from barug.containers import app


def test_audience_backend():
    """Test the audience backend functionality"""
    
    # Get services from DI container
    announcement_service = app.announcement_service()
    audience_service = app.audience_service()
    
    print("=== Testing Audience Backend ===\n")
    
    try:
        # 1. Create a test announcement
        print("1. Creating test announcement...")
        announcement_cmd = CreateAnnouncementDraftCMD(
            title="Test Announcement",
            body="This is a test announcement for audience testing",
            created_by_id=1  # Assuming staff ID 1 exists
        )
        
        announcement_id = announcement_service.create_draft(announcement_cmd)
        print(f"   ✓ Created announcement ID: {announcement_id}")
        
        # 2. Test supported audience scopes (1 and 2 only)
        supported_cases = [
            {"scope_id": 1, "name": "ALL ACTIVE", "role_id": None, "purok_id": None},
            {"scope_id": 2, "name": "RESIDENTS", "role_id": None, "purok_id": None},
        ]
        
        print("\n2. Testing supported audience scopes...")
        for test_case in supported_cases:
            try:
                audience_cmd = AddAnnouncementAudienceCMD(
                    announcement_id=announcement_id,
                    audience_scope_id=test_case["scope_id"],
                    role_id=test_case["role_id"],
                    purok_sitio_id=test_case["purok_id"]
                )
                
                audience_id, inserted_persons = audience_service.add_announcement_audience(audience_cmd)
                print(f"   ✓ {test_case['name']}: Audience ID {audience_id}, {inserted_persons} persons")
                
            except Exception as e:
                print(f"   ✗ {test_case['name']}: {str(e)}")
        
        # 3. Test unsupported scopes (should fail with expected error)
        unsupported_cases = [
            {"scope_id": 3, "name": "STAFF"},
            {"scope_id": 7, "name": "BUSINESS OWNERS"},
            {"scope_id": 8, "name": "PUROK"},
        ]
        
        print("\n3. Testing unsupported audience scopes (should fail)...")
        for test_case in unsupported_cases:
            try:
                audience_cmd = AddAnnouncementAudienceCMD(
                    announcement_id=announcement_id,
                    audience_scope_id=test_case["scope_id"]
                )
                
                audience_service.add_announcement_audience(audience_cmd)
                print(f"   ✗ {test_case['name']}: Expected error but succeeded")
                
            except Exception as e:
                if "only supports audience_scope_id 1" in str(e):
                    print(f"   ✓ {test_case['name']}: Correctly rejected (not implemented)")
                else:
                    print(f"   ✗ {test_case['name']}: Unexpected error: {str(e)}")
        
        # 4. Get audience scopes
        print("\n4. Getting available audience scopes...")
        scopes = audience_service.get_audience_scopes()
        for scope in scopes:
            print(f"   - {scope.audience_scope_id}: {scope.audience_scope_name}")
        
        # 5. Get announcement audiences
        print(f"\n5. Getting audiences for announcement {announcement_id}...")
        audiences = audience_service.get_announcement_audiences(announcement_id)
        if audiences:
            for audience in audiences:
                print(f"   - Audience {audience.audience_id}: {audience.audience_scope_name} ({audience.inserted_persons} persons)")
        else:
            print("   No audiences found for this announcement")
        
        print("\n=== Test Completed ===\nNote: Only scope IDs 1 (ALL) and 2 (RESIDENTS) are currently supported by the database function.")
        
    except Exception as e:
        print(f"\n✗ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_audience_backend()