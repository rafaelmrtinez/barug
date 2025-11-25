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
from src.app.transfer_objects.dto.publish_result_dto import PublishResultDTO
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