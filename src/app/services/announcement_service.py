from typing import List, Optional
from src.app.contracts.announcement_service_contract import IAnnouncementService
from src.domain.contracts.announcement_repository_contract import IAnnouncementRepository
from src.app.transfer_objects.dto.announcement_dto import (
    AnnouncementDTO
)
from src.app.transfer_objects.commands.announcement_cmd import (
    CreateAnnouncementDraftCMD, 
    UpdateAnnouncementDraftCMD, 
    PublishAnnouncementCMD,
)


class AnnouncementService(IAnnouncementService):
    """Service implementation for announcement business logic"""

    def __init__(self, announcement_repository: IAnnouncementRepository):
        self.announcement_repository = announcement_repository

    def create_draft(self, command: CreateAnnouncementDraftCMD) -> int:
        """Create a new announcement draft with validation"""
        # Basic validation
        if not command.title or not command.title.strip():
            raise ValueError("Announcement title is required")
        
        if not command.body or not command.body.strip():
            raise ValueError("Announcement body is required")
        
        if not command.created_by_id:
            raise ValueError("Creator ID is required")
        
        # Validate date logic if both dates are provided
        if command.publish_at and command.expire_at:
            if command.expire_at <= command.publish_at:
                raise ValueError("Expiry date must be after publish date")
        
        return self.announcement_repository.create_draft(command)

    def update_draft(self, command: UpdateAnnouncementDraftCMD) -> bool:
        """Update an existing announcement draft with validation"""
        # Basic validation
        if not command.title or not command.title.strip():
            raise ValueError("Announcement title is required")
        
        if not command.body or not command.body.strip():
            raise ValueError("Announcement body is required")
        
        # Validate date logic if both dates are provided
        if command.publish_at and command.expire_at:
            if command.expire_at <= command.publish_at:
                raise ValueError("Expiry date must be after publish date")
        
        # Check if draft exists
        existing = self.announcement_repository.get_by_id(command.announcement_id)
        if not existing:
            raise ValueError("Announcement not found")
        
        if existing.announcement_status_id != 1:  # Not a draft
            raise ValueError("Can only update draft announcements")
        
        return self.announcement_repository.update_draft(command)

    def get_draft_by_id(self, announcement_id: int) -> Optional[AnnouncementDTO]:
        """Get announcement draft by ID"""
        if not announcement_id:
            return None
        
        announcement = self.announcement_repository.get_by_id(announcement_id)
        
        # Only return if it's a draft
        if announcement and announcement.announcement_status_id == 1:
            return announcement
        
        return None

    def get_drafts_by_creator(self, created_by_id: int) -> List[AnnouncementDTO]:
        """Get all drafts created by a specific user"""
        if not created_by_id:
            return []
        
        return self.announcement_repository.get_drafts_by_creator(created_by_id)

    def get_all_drafts(self) -> List[AnnouncementDTO]:
        """Get all announcement drafts"""
        return self.announcement_repository.get_all_drafts()

    def publish_announcement(self, command: PublishAnnouncementCMD) -> bool:
        """Publish an announcement with validation"""
        if not command.announcement_id:
            raise ValueError("Announcement ID is required")
        
        if not command.published_by_id:
            raise ValueError("Publisher ID is required")
        
        # Check if announcement exists and is a draft
        existing = self.announcement_repository.get_by_id(command.announcement_id)
        if not existing:
            raise ValueError("Announcement not found")
        
        if existing.announcement_status_id != 1:  # Not a draft
            raise ValueError("Can only publish draft announcements")
        
        return self.announcement_repository.publish_announcement(
            command.announcement_id, 
            command.published_by_id
        )

    def delete_draft(self, announcement_id: int) -> bool:
        """Delete an announcement draft with validation"""
        if not announcement_id:
            raise ValueError("Announcement ID is required")
        
        # Check if draft exists
        existing = self.announcement_repository.get_by_id(announcement_id)
        if not existing:
            raise ValueError("Announcement not found")
        
        if existing.announcement_status_id != 1:  # Not a draft
            raise ValueError("Can only delete draft announcements")
        
        return self.announcement_repository.delete_draft(announcement_id)
    
    def search_drafts(self, search_query: str) -> List[AnnouncementDTO]:
        """Search announcement drafts by title or body"""
        if not search_query or not search_query.strip():
            return self.get_all_drafts()
        
        return self.announcement_repository.search_drafts(search_query.strip())
    
    def execute(
            self,
            search: Optional[str],
    ) -> List[AnnouncementDTO]:
        """Execute the search and return the results"""
        if search:
            return self.search_drafts(search)
        return self.get_all_drafts()