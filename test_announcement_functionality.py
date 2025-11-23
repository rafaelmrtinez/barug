#!/usr/bin/env python3
"""
Test script to demonstrate the announcement draft functionality.
This shows how to use the announcement service to create and manage drafts.
"""

import os
import sys
import django
from datetime import datetime, timedelta

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'barug.settings')
django.setup()

def test_announcement_functionality():
    """Test the announcement draft functionality"""
    
    # Import the required modules after Django setup
    from barug.containers import app
    from src.app.transfer_objects.commands.announcement_cmd import CreateAnnouncementDraftCMD
    
    print("🚀 Testing Announcement Draft Functionality")
    print("=" * 50)
    
    try:
        # Get the announcement service from the DI container
        announcement_service = app.announcement_service()
        print("✅ Successfully retrieved announcement service from DI container")
        
        # Test 1: Create a basic draft
        print("\n📝 Test 1: Creating a basic announcement draft...")
        
        command = CreateAnnouncementDraftCMD(
            title="Test Announcement",
            body="This is a test announcement body with some content to demonstrate the functionality.",
            created_by_id=1,  # Assuming staff ID 1 exists
            publish_at=None,  # Keep as draft
            expire_at=None
        )
        
        draft_id = announcement_service.create_draft(command)
        print(f"✅ Created draft with ID: {draft_id}")
        
        # Test 2: Create a scheduled draft
        print("\n📅 Test 2: Creating a scheduled announcement draft...")
        
        publish_time = datetime.now() + timedelta(hours=1)
        expire_time = datetime.now() + timedelta(days=7)
        
        scheduled_command = CreateAnnouncementDraftCMD(
            title="Scheduled Community Meeting",
            body="Join us for our monthly community meeting to discuss important barangay matters.",
            created_by_id=1,
            publish_at=publish_time,
            expire_at=expire_time
        )
        
        scheduled_id = announcement_service.create_draft(scheduled_command)
        print(f"✅ Created scheduled draft with ID: {scheduled_id}")
        print(f"   📅 Publish at: {publish_time.strftime('%Y-%m-%d %H:%M')}")
        print(f"   ⏰ Expire at: {expire_time.strftime('%Y-%m-%d %H:%M')}")
        
        # Test 3: Retrieve all drafts
        print("\n📋 Test 3: Retrieving all drafts...")
        
        all_drafts = announcement_service.get_all_drafts()
        print(f"✅ Found {len(all_drafts)} total drafts")
        
        for draft in all_drafts[-2:]:  # Show last 2 drafts
            print(f"   📄 ID: {draft.announcement_id}")
            print(f"      Title: {draft.announcement_title}")
            print(f"      Created: {draft.announcement_created_at}")
            print(f"      Status: {draft.announcement_status_name}")
            print()
        
        # Test 4: Retrieve drafts by creator
        print("👤 Test 4: Retrieving drafts by creator...")
        
        creator_drafts = announcement_service.get_drafts_by_creator(1)
        print(f"✅ Found {len(creator_drafts)} drafts created by user ID 1")
        
        # Test 5: Get specific draft
        print(f"\n🔍 Test 5: Retrieving specific draft (ID: {draft_id})...")
        
        specific_draft = announcement_service.get_draft_by_id(draft_id)
        if specific_draft:
            print("✅ Successfully retrieved draft:")
            print(f"   Title: {specific_draft.announcement_title}")
            print(f"   Body: {specific_draft.announcement_body[:50]}...")
            print(f"   Created: {specific_draft.announcement_created_at}")
        else:
            print("❌ Draft not found")
        
        print("\n🎉 All tests completed successfully!")
        print("\n💡 Usage Instructions:")
        print("1. Navigate to /secretary/announcement/create_draft/ to create drafts")
        print("2. Navigate to /secretary/announcement/draft_list/ to view all drafts")
        print("3. Use the Django admin or database to manage announcement_status table")
        
    except Exception as e:
        print(f"❌ Error during testing: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_announcement_functionality()