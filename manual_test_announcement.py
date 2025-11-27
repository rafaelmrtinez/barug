#!/usr/bin/env python3
"""
Manual test to force publish and process a specific announcement
"""
import os
import sys
import django

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'barug.settings')
django.setup()

from src.infra.database.connection_adapter import ConnectionAdapter
from src.infra.repositories.announcement_repository import AnnouncementRepository

def manual_test():
    ctx = ConnectionAdapter()
    announcement_repo = AnnouncementRepository(ctx)
    
    announcement_id = 42  # Your scheduled announcement
    
    print(f"Manual test for announcement {announcement_id}")
    
    # Step 1: Use the database function to publish
    print("1. Using publish_announcement_now function...")
    try:
        publish_sql = "SELECT * FROM publish_announcement_now(%s, %s)"
        result = ctx.execute_query(publish_sql, (announcement_id, 1))  # user_id = 1
        if result:
            print(f"   Published with {result[0][1]} recipients")
        else:
            print("   Failed to publish")
    except Exception as e:
        print(f"   Error: {e}")
        # Fallback: manually update status
        print("   Trying manual status update...")
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE announcement SET announcement_status_id = 3, updated_at = now() WHERE announcement_id = %s",
                    [announcement_id]
                )
            print("   Status updated manually")
        except Exception as e2:
            print(f"   Manual update failed: {e2}")
    
    # Step 2: Create recipients (if not already created)
    print("2. Creating recipients...")
    try:
        create_sql = "SELECT create_announcement_recipients(%s)"
        result = ctx.execute_query(create_sql, (announcement_id,))
        recipients_created = result[0][0] if result else 0
        print(f"   Created {recipients_created} recipients")
    except Exception as e:
        print(f"   Error creating recipients: {e}")
        recipients_created = 0
    
    # Check if recipients exist
    check_sql = "SELECT COUNT(*) FROM announcement_recipient WHERE announcement_id = %s"
    check_result = ctx.execute_query(check_sql, (announcement_id,))
    existing_recipients = check_result[0][0] if check_result else 0
    print(f"   Total recipients in database: {existing_recipients}")
    
    # Step 3: Check recipient statuses first
    print("3. Checking recipient statuses...")
    status_check_sql = """
        SELECT ar.announcement_deliver_status_id, ads.announcement_deliver_status_name, COUNT(*)
        FROM announcement_recipient ar
        JOIN announcement_deliver_status ads ON ads.announcement_deliver_status_id = ar.announcement_deliver_status_id
        WHERE ar.announcement_id = %s
        GROUP BY ar.announcement_deliver_status_id, ads.announcement_deliver_status_name
    """
    status_check_result = ctx.execute_query(status_check_sql, (announcement_id,))
    
    for row in status_check_result:
        print(f"   Status {row[0]} ({row[1]}): {row[2]} recipients")
    
    # Step 4: Force email sending for all recipients
    print("4. Force sending emails to all recipients...")
    force_email_sql = """
        SELECT ar.announcement_recipient_id, ar.channel_type_id,
               p.email, p.mobile_num, p.first_name, p.last_name,
               a.announcement_title, a.announcement_body
        FROM announcement_recipient ar
        JOIN person p ON p.person_id = ar.person_id
        JOIN announcement a ON a.announcement_id = ar.announcement_id
        WHERE ar.announcement_id = %s
        AND ar.channel_type_id = 2
        AND p.email IS NOT NULL
    """
    
    email_recipients = ctx.execute_query(force_email_sql, (announcement_id,))
    
    if email_recipients:
        from common.send_email import send_email
        from common.email_validator import verify_email_deliverable_abstract
        
        for recipient in email_recipients:
            recipient_id, channel_type, email, mobile, first_name, last_name, title, body = recipient
            
            print(f"   Sending email to: {email}")
            
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
                    print(f"     ✅ Email sent successfully")
                else:
                    print(f"     ❌ Invalid email address")
            except Exception as e:
                print(f"     ❌ Error sending email: {e}")
    else:
        print("   No email recipients found")
    
    # Step 5: Final delivery status
    print("5. Final delivery status...")
    status_sql = """
        SELECT ads.announcement_deliver_status_name, COUNT(*)
        FROM announcement_recipient ar
        JOIN announcement_deliver_status ads ON ads.announcement_deliver_status_id = ar.announcement_deliver_status_id
        WHERE ar.announcement_id = %s
        GROUP BY ads.announcement_deliver_status_name
    """
    status_result = ctx.execute_query(status_sql, (announcement_id,))
    
    for row in status_result:
        print(f"   {row[0]}: {row[1]}")
    
    print("\n✅ Manual test completed!")

if __name__ == "__main__":
    manual_test()