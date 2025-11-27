from typing import List, Optional
from datetime import datetime
from src.domain.contracts.announcement_repository_contract import IAnnouncementRepository
from src.app.transfer_objects.dto.announcement_dto import (
    AnnouncementDTO,
    AnnouncementStatusDTO
)
from src.app.transfer_objects.commands.announcement_cmd import (
    CreateAnnouncementDraftCMD,
    PublishAnnouncementCMD,
    UpdateAnnouncementDraftCMD,
)
from src.app.transfer_objects.commands.publish_now_cmd import PublishAnnouncementNowCMD
from src.app.transfer_objects.commands.schedule_cmd import ScheduleAnnouncementCMD
from src.app.transfer_objects.dto.publish_result_dto import PublishResultDTO
from src.app.transfer_objects.dto.schedule_result_dto import ScheduleResultDTO
from common.send_email import send_email
from common.send_sms import send_sms
from common.email_validator import verify_email_deliverable_abstract
from src.infra.contracts.connection_adapter import IConnectionAdapter


class AnnouncementRepository(IAnnouncementRepository):
    """Concrete implementation of announcement repository"""

    def __init__(self, ctx: IConnectionAdapter):
        self.ctx = ctx

    def create_draft(self, command: CreateAnnouncementDraftCMD) -> int:
        """Create a new announcement draft and return the ID"""
        sql = """
            INSERT INTO public.announcement (
                announcement_title, 
                announcement_body, 
                announcement_created_at, 
                announcement_status_id, 
                announcement_published_at, 
                announcement_expire_at, 
                created_by_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING announcement_id
        """
        
        # Status ID 1 = Draft (assuming this exists in announcement_status table)
        status_id = 1
        created_at = datetime.now()
        
        params = (
            command.title,
            command.body,
            created_at,
            status_id,
            command.publish_at,
            command.expire_at,
            command.created_by_id
        )
        
        result = self.ctx.execute_query(sql, params)
        return result[0][0] if result else None

    def update_draft(self, command: UpdateAnnouncementDraftCMD) -> bool:
        """Update an existing announcement draft"""
        sql = """
            UPDATE public.announcement 
            SET announcement_title = %s,
                announcement_body = %s,
                announcement_published_at = %s,
                announcement_expire_at = %s
            WHERE announcement_id = %s 
            AND announcement_status_id = 1
        """
        
        params = (
            command.title,
            command.body,
            command.publish_at,
            command.expire_at,
            command.announcement_id
        )
        
        result = self.ctx.execute_query(sql, params)
        return result is not None

    def get_by_id(self, announcement_id: int) -> Optional[AnnouncementDTO]:
        """Get announcement by ID"""
        sql = """
            SELECT a.announcement_id, a.announcement_title, a.announcement_body,
                   a.announcement_created_at, a.announcement_status_id,
                   a.announcement_published_at, a.announcement_expire_at,
                   a.created_by_id, a.published_by_id,
                   ast.announcement_status_name
            FROM public.announcement a
            LEFT JOIN public.announcement_status ast ON a.announcement_status_id = ast.announcement_status_id
            WHERE a.announcement_id = %s
        """
        
        result = self.ctx.execute_query(sql, (announcement_id,))
        if not result:
            return None
            
        row = result[0]
        return AnnouncementDTO(
            announcement_id=row[0],
            announcement_title=row[1],
            announcement_body=row[2],
            announcement_created_at=row[3],
            announcement_status_id=row[4],
            announcement_published_at=row[5],
            announcement_expire_at=row[6],
            created_by_id=row[7],
            published_by_id=row[8],
            announcement_status_name=row[9]
        )

    def get_drafts_by_creator(self, created_by_id: int) -> List[AnnouncementDTO]:
        """Get all drafts created by a specific user"""
        sql = """
            SELECT a.announcement_id, a.announcement_title, a.announcement_body,
                   a.announcement_created_at, a.announcement_status_id,
                   a.announcement_published_at, a.announcement_expire_at,
                   a.created_by_id, a.published_by_id,
                   ast.announcement_status_name
            FROM public.announcement a
            LEFT JOIN public.announcement_status ast ON a.announcement_status_id = ast.announcement_status_id
            WHERE a.created_by_id = %s AND a.announcement_status_id = 1
            ORDER BY a.announcement_created_at DESC
        """
        
        result = self.ctx.execute_query(sql, (created_by_id,))
        return [
            AnnouncementDTO(
                announcement_id=row[0],
                announcement_title=row[1],
                announcement_body=row[2],
                announcement_created_at=row[3],
                announcement_status_id=row[4],
                announcement_published_at=row[5],
                announcement_expire_at=row[6],
                created_by_id=row[7],
                published_by_id=row[8],
                announcement_status_name=row[9]
            )
            for row in result
        ]

    def get_all_drafts(self) -> List[AnnouncementDTO]:
        """Get all announcement drafts"""
        sql = """
            SELECT a.announcement_id, a.announcement_title, a.announcement_body,
                   a.announcement_created_at, a.announcement_status_id,
                   a.announcement_published_at, a.announcement_expire_at,
                   a.created_by_id, a.published_by_id,
                   ast.announcement_status_name
            FROM public.announcement a
            LEFT JOIN public.announcement_status ast ON a.announcement_status_id = ast.announcement_status_id
            WHERE a.announcement_status_id = 1
            ORDER BY a.announcement_created_at DESC
        """
        
        result = self.ctx.execute_query(sql)
        return [
            AnnouncementDTO(
                announcement_id=row[0],
                announcement_title=row[1],
                announcement_body=row[2],
                announcement_created_at=row[3],
                announcement_status_id=row[4],
                announcement_published_at=row[5],
                announcement_expire_at=row[6],
                created_by_id=row[7],
                published_by_id=row[8],
                announcement_status_name=row[9]
            )
            for row in result
        ]

    def publish_announcement(self, announcement_id: int, published_by_id: int) -> bool:
        """Publish an announcement"""
        sql = """
            UPDATE public.announcement 
            SET announcement_status_id = 2,
                published_by_id = %s,
                announcement_published_at = COALESCE(announcement_published_at, %s)
            WHERE announcement_id = %s
        """
        
        published_at = datetime.now()
        params = (published_by_id, published_at, announcement_id)
        
        result = self.ctx.execute_query(sql, params)
        return result is not None
    
    def publish_announcement_now(self, command: PublishAnnouncementNowCMD) -> PublishResultDTO:
        """Publish an announcement immediately using the database function"""
        sql = "SELECT * FROM publish_announcement_now(%s, %s)"
        params = (command.announcement_id, command.published_by_id)
        
        result = self.ctx.execute_query(sql, params)
        if not result:
            raise ValueError("Failed to publish announcement")
        
        row = result[0]
        announcement_id = row[0]
        total_recipients = row[1]
        
        # Send notifications based on enabled channels
        self._send_notifications(announcement_id)
        
        return PublishResultDTO(
            announcement_id=announcement_id,
            total_recipients=total_recipients
        )
    
    def _send_notifications(self, announcement_id: int) -> None:
        """Send email/SMS notifications based on enabled channels"""
        # Get announcement details
        announcement_sql = "SELECT announcement_title, announcement_body FROM announcement WHERE announcement_id = %s"
        announcement_result = self.ctx.execute_query(announcement_sql, (announcement_id,))
        if not announcement_result:
            return
        
        title, body = announcement_result[0]
        
        # Get recipients by channel type
        recipients_sql = """
            SELECT ar.channel_type_id, p.email, p.mobile_num, p.first_name, p.last_name
            FROM announcement_recipient ar
            JOIN person p ON p.person_id = ar.person_id
            WHERE ar.announcement_id = %s 
            AND ar.announcement_deliver_status_id IN (2, 3, 4)
        """
        recipients = self.ctx.execute_query(recipients_sql, (announcement_id,))
        
        if not recipients:
            return
        
        # Group recipients by channel type
        email_recipients = []
        sms_recipients = []
        
        for channel_type_id, email, mobile, first_name, last_name in recipients:
            if channel_type_id == 2 and email:  # EMAIL
                is_valid, _ = verify_email_deliverable_abstract(email)
                if is_valid:
                    name = f"{first_name or ''} {last_name or ''}".strip()
                    email_recipients.append((name, email) if name else email)
            elif channel_type_id == 1 and mobile:  # SMS
                sms_recipients.append(mobile)
        
        # Send emails
        if email_recipients:
            try:
                send_email(
                    subject=f"Announcement: {title}",
                    to=email_recipients,
                    body_text=body,
                    fail_silently=True
                )
            except Exception:
                pass  # Log if needed, but don't fail the publish
        
        # # Send SMS
        # if sms_recipients:
        #     try:
        #         sms_message = f"{title}\n\n{body}"
        #         if len(sms_message) > 160:
        #             sms_message = sms_message[:157] + "..."
        #         send_sms(
        #             to=sms_recipients,
        #             message=sms_message,
        #             fail_silently=True
        #         )
        #     except Exception:
        #         pass  # Log if needed, but don't fail the publish
    
    def schedule_announcement(self, command: ScheduleAnnouncementCMD) -> ScheduleResultDTO:
        """Schedule an announcement using the database function"""
        sql = "SELECT * FROM schedule_announcement(%s, %s)"
        params = (command.announcement_id, command.scheduled_by_id)
        
        result = self.ctx.execute_query(sql, params)
        if not result:
            raise ValueError("Failed to schedule announcement")
        
        row = result[0]
        announcement_id = row[0]
        
        return ScheduleResultDTO(
            announcement_id=announcement_id,
            new_status=row[1],
            publish_at=row[2]
        )
    
    def _process_pending_deliveries(self, announcement_id: int) -> None:
        """Process deliveries and send actual notifications"""
        # Get ALL recipients for this announcement (not just pending)
        sql = """
            SELECT ar.announcement_recipient_id, ar.channel_type_id, ar.announcement_deliver_status_id,
                   p.email, p.mobile_num, p.first_name, p.last_name,
                   a.announcement_title, a.announcement_body
            FROM announcement_recipient ar
            JOIN person p ON p.person_id = ar.person_id
            JOIN announcement a ON a.announcement_id = ar.announcement_id
            WHERE ar.announcement_id = %s
            AND ar.channel_type_id = 2
            AND p.email IS NOT NULL
        """
        
        recipients = self.ctx.execute_query(sql, (announcement_id,))
        
        print(f"   Found {len(recipients)} email recipients for announcement {announcement_id}")
        
        for recipient in recipients:
            recipient_id, channel_type, current_status, email, mobile, first_name, last_name, title, body = recipient
            
            print(f"     Processing recipient: {email} (current status: {current_status})")
            
            try:
                success = self._send_email_notification(email, first_name, last_name, title, body)
                
                if success:
                    print(f"       ✅ Email sent successfully")
                    self._update_delivery_status(recipient_id, 3, None)  # SENT EMAIL
                else:
                    print(f"       ❌ Email sending failed")
                    self._update_delivery_status(recipient_id, 5, "Email delivery failed")
                    
            except Exception as e:
                print(f"       ❌ Error: {e}")
                self._update_delivery_status(recipient_id, 5, str(e))
                success = self._send_email_notification(email, first_name, last_name, title, body)
                
                # Update delivery status
                if success:
                    status_id = 2 if channel_type == 1 else 3 if channel_type == 2 else 4
                    self._update_delivery_status(recipient_id, status_id, None)
                else:
                    self._update_delivery_status(recipient_id, 5, "Delivery failed")
                
    
    def _send_email_notification(self, email: str, first_name: str, last_name: str, title: str, body: str) -> bool:
        try:
            is_valid, _ = verify_email_deliverable_abstract(email)
            if not is_valid:
                return False
            
            name = f"{first_name or ''} {last_name or ''}".strip()
            recipient = (name, email) if name else email
            
            send_email(
                subject=f"Announcement: {title}",
                to=[recipient],
                body_text=body,
                fail_silently=False
            )
            return True
        except:
            return False
    
    def _send_sms_notification(self, mobile: str, title: str, body: str) -> bool:
        # SMS is commented out in your code, so just return True for now
        return True
    
    def _update_delivery_status(self, recipient_id: int, status_id: int, error: str):
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE announcement_recipient 
                SET announcement_deliver_status_id = %s,
                    delivery_error = %s,
                    delivered_at = CASE WHEN %s IN (2,3,4) THEN now() ELSE NULL END,
                    updated_at = now()
                WHERE announcement_recipient_id = %s
                """,
                [status_id, error, status_id, recipient_id]
            )

    def get_announcement_statuses(self) -> List[AnnouncementStatusDTO]:
        """Get all announcement statuses"""
        sql = """
            SELECT announcement_status_id, announcement_status_name
            FROM public.announcement_status
            ORDER BY announcement_status_id
        """
        
        result = self.ctx.execute_query(sql)
        return [
            AnnouncementStatusDTO(
                announcement_status_id=row['announcement_status_id'],
                announcement_status_name=row['announcement_status_name']
            )
            for row in result
        ]

    def search_drafts(self, search: str) -> List[AnnouncementDTO]:
        """
        Search announcement drafts (status = 1) by title or body using ILIKE.
        If search is empty or None, returns all drafts.
        """
        # normalize input
        if not search or not search.strip():
            return self.get_all_drafts()

        like_pattern = f"%{search.strip()}%"

        sql = """
            SELECT a.announcement_id, a.announcement_title, a.announcement_body,
                   a.announcement_created_at, a.announcement_status_id,
                   a.announcement_published_at, a.announcement_expire_at,
                   a.created_by_id, a.published_by_id,
                   ast.announcement_status_name
            FROM public.announcement a
            LEFT JOIN public.announcement_status ast ON a.announcement_status_id = ast.announcement_status_id
            WHERE a.announcement_status_id = 1
              AND (a.announcement_title ILIKE %s OR a.announcement_body ILIKE %s)
            ORDER BY a.announcement_created_at DESC
        """

        params = (like_pattern, like_pattern)
        result = self.ctx.execute_query(sql, params)

        if not result:
            return []

        return [
            AnnouncementDTO(
                announcement_id=row[0],
                announcement_title=row[1],
                announcement_body=row[2],
                announcement_created_at=row[3],
                announcement_status_id=row[4],
                announcement_published_at=row[5],
                announcement_expire_at=row[6],
                created_by_id=row[7],
                published_by_id=row[8],
                announcement_status_name=row[9]
            )
            for row in result
        ]
       

    def delete_draft(self, announcement_id: int) -> bool:
        """Delete an announcement draft"""
        sql = """
            DELETE FROM public.announcement 
            WHERE announcement_id = %s AND announcement_status_id = 1
        """
        
        result = self.ctx.execute_query(sql, (announcement_id,))
        return result is not None