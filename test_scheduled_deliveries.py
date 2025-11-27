#!/usr/bin/env python3
"""
Local test script for scheduled deliveries
Run this to test the delivery process without web cron
"""
import os
import sys
import django
import time
from datetime import datetime

# Add the project directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'barug.settings')
django.setup()

from src.infra.database.connection_adapter import ConnectionAdapter
from src.infra.repositories.announcement_repository import AnnouncementRepository

def test_scheduled_deliveries():
    """Test the scheduled delivery process"""
    print("Testing scheduled deliveries...")
    
    ctx = ConnectionAdapter()
    announcement_repo = AnnouncementRepository(ctx)
    
    # Debug: Check what scheduled announcements exist
    print("Debug: Checking scheduled announcements...")
    debug_sql = """
        SELECT announcement_id, announcement_title, announcement_status_id, 
               announcement_published_at, announcement_expire_at, now() as current_time,
               CASE WHEN announcement_published_at <= now() THEN 'READY' ELSE 'NOT READY' END as ready_status
        FROM announcement 
        WHERE announcement_status_id = 2
    """
    debug_result = ctx.execute_query(debug_sql)
    
    if debug_result:
        print("   Found scheduled announcements:")
        for row in debug_result:
            print(f"     ID: {row[0]}, Title: {row[1][:30] if row[1] else 'No title'}..., Status: {row[2]}")
            print(f"     Publish at: {row[3]}")
            print(f"     Current time: {row[5]}")
            print(f"     Ready to publish: {row[6]}")
            print(f"     Expire at: {row[4]}")
            print("     ---")
    else:
        print("   No scheduled announcements found (status = 2)")
    
    # Also check all announcements to see what exists
    print("\nDebug: All announcements:")
    all_sql = """
        SELECT announcement_id, announcement_title, announcement_status_id, 
               announcement_published_at, now() as current_time
        FROM announcement 
        ORDER BY announcement_created_at DESC
        LIMIT 5
    """
    all_result = ctx.execute_query(all_sql)
    
    if all_result:
        for row in all_result:
            print(f"   ID: {row[0]}, Status: {row[2]}, Title: {row[1][:30] if row[1] else 'No title'}...")
            print(f"   Publish at: {row[3]}, Now: {row[4]}")
    else:
        print("   No announcements found at all")
    
    # Check if there are announcements ready soon and wait for them
    wait_sql = """
        SELECT announcement_id, announcement_title, announcement_published_at,
               EXTRACT(EPOCH FROM (announcement_published_at - now())) as seconds_until
        FROM announcement 
        WHERE announcement_status_id = 2
        AND announcement_published_at > now()
        AND announcement_published_at <= now() + interval '2 minutes'
        ORDER BY announcement_published_at
        LIMIT 1
    """
    
    wait_result = ctx.execute_query(wait_sql)
    
    if wait_result:
        row = wait_result[0]
        announcement_id = row[0]
        title = row[1]
        publish_time = row[2]
        seconds_until = int(row[3])
        
        if seconds_until > 0:
            print(f"\nFound announcement '{title[:30]}...' scheduled in {seconds_until} seconds")
            print(f"Waiting until {publish_time}...")
            
            # Countdown
            for i in range(seconds_until, 0, -1):
                print(f"\rCountdown: {i} seconds remaining...", end="", flush=True)
                time.sleep(1)
            print("\rTime reached! Processing...")
    
    # Step 1: Publish any scheduled announcements
    print("\n1. Publishing scheduled announcements...")
    
    # Debug: Check what the function sees
    debug_publish_sql = """
        SELECT announcement_id, announcement_status_id, announcement_published_at, 
               announcement_expire_at, now() as current_time,
               CASE WHEN announcement_published_at <= now() THEN 'TIME OK' ELSE 'TIME NOT OK' END as time_check
        FROM announcement 
        WHERE announcement_status_id = 2
        AND announcement_published_at IS NOT NULL
    """
    debug_publish_result = ctx.execute_query(debug_publish_sql)
    
    if debug_publish_result:
        print("   Debug - What publish function sees:")
        for row in debug_publish_result:
            print(f"     ID: {row[0]}, Status: {row[1]}, Time check: {row[5]}")
            print(f"     Publish: {row[2]}, Now: {row[4]}")
    
    publish_sql = "SELECT * FROM publish_scheduled_announcements()"
    publish_result = ctx.execute_query(publish_sql)
    
    if publish_result:
        published_count = publish_result[0][0]
        total_recipients = publish_result[0][1]
        print(f"   Published {published_count} announcements with {total_recipients} recipients")
        
        # If nothing was published, check why
        if published_count == 0:
            print("   Debug - Checking why nothing was published...")
            # Check audience
            audience_sql = "SELECT COUNT(*) FROM audience WHERE announcement_id = 42"
            audience_result = ctx.execute_query(audience_sql)
            print(f"     Audiences for announcement 42: {audience_result[0][0] if audience_result else 0}")
            
            # Check audience_person_list
            person_sql = """
                SELECT COUNT(*) FROM audience a 
                JOIN audience_person_list apl ON apl.audience_id = a.audience_id 
                WHERE a.announcement_id = 42
            """
            person_result = ctx.execute_query(person_sql)
            print(f"     People in audiences: {person_result[0][0] if person_result else 0}")
            
            # Check channels
            channel_sql = "SELECT COUNT(*) FROM announcement_channel WHERE announcement_id = 42 AND is_enabled = TRUE"
            channel_result = ctx.execute_query(channel_sql)
            print(f"     Enabled channels: {channel_result[0][0] if channel_result else 0}")
    else:
        print("   No scheduled announcements to publish")
    
    # Step 2: Process pending deliveries
    print("2. Processing pending deliveries...")
    delivery_sql = """
        SELECT DISTINCT ar.announcement_id
        FROM announcement_recipient ar
        JOIN announcement a ON a.announcement_id = ar.announcement_id
        WHERE ar.announcement_deliver_status_id = 1
        AND a.announcement_status_id = 3
    """
    
    delivery_result = ctx.execute_query(delivery_sql)
    processed_count = 0
    
    for row in delivery_result:
        announcement_id = row[0]
        print(f"   Processing deliveries for announcement {announcement_id}")
        announcement_repo._process_pending_deliveries(announcement_id)
        processed_count += 1
    
    print(f"   Processed deliveries for {processed_count} announcements")
    
    # If no pending deliveries, force send emails to recently published announcements
    if processed_count == 0:
        print("   No pending deliveries found. Checking for recently published announcements...")
        
        recent_sql = """
            SELECT DISTINCT ar.announcement_id
            FROM announcement_recipient ar
            JOIN announcement a ON a.announcement_id = ar.announcement_id
            WHERE a.announcement_status_id = 3
            AND a.announcement_published_at >= now() - interval '10 minutes'
        """
        
        recent_result = ctx.execute_query(recent_sql)
        
        for row in recent_result:
            announcement_id = row[0]
            print(f"   Force sending emails for announcement {announcement_id}...")
            
            # Get email recipients
            email_sql = """
                SELECT ar.announcement_recipient_id, p.email, p.first_name, p.last_name,
                       a.announcement_title, a.announcement_body
                FROM announcement_recipient ar
                JOIN person p ON p.person_id = ar.person_id
                JOIN announcement a ON a.announcement_id = ar.announcement_id
                WHERE ar.announcement_id = %s
                AND ar.channel_type_id = 2
                AND p.email IS NOT NULL
            """
            
            email_recipients = ctx.execute_query(email_sql, (announcement_id,))
            
            if email_recipients:
                from common.send_email import send_email
                from common.email_validator import verify_email_deliverable_abstract
                
                for recipient in email_recipients:
                    recipient_id, email, first_name, last_name, title, body = recipient
                    
                    print(f"     Sending to: {email}")
                    
                    try:
                        is_valid, _ = verify_email_deliverable_abstract(email)
                        if is_valid:
                            name = f"{first_name or ''} {last_name or ''}".strip()
                            recipient_addr = (name, email) if name else email
                            
                            send_email(
                                subject=f"Announcement: {title}",
                                to=[recipient_addr],
                                body_text=body,
                                fail_silently=False
                            )
                            print(f"       ✅ Email sent successfully")
                        else:
                            print(f"       ❌ Invalid email address")
                    except Exception as e:
                        print(f"       ❌ Error: {e}")
            else:
                print(f"     No email recipients found for announcement {announcement_id}")
    
    # Step 3: Show delivery summary
    if processed_count > 0:
        print("3. Delivery summary:")
        for row in delivery_result:
            announcement_id = row[0]
            summary_sql = "SELECT * FROM announcement_delivery_summary(%s)"
            summary_result = ctx.execute_query(summary_sql, (announcement_id,))
            print(f"   Announcement {announcement_id}:")
            for status_row in summary_result:
                print(f"     {status_row[0]}: {status_row[1]}")
    
    print("\n✅ Test completed! Check your email for delivery notifications.")
    print("   If you see '[EMAIL DEBUG] send_email()' logs above, emails were sent.")

if __name__ == "__main__":
    try:
        test_scheduled_deliveries()
    except KeyboardInterrupt:
        print("\n\n❌ Test interrupted by user")