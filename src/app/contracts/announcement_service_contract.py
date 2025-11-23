from abc import ABC, abstractmethod
from typing import List, Optional
from src.app.transfer_objects.dto.announcement_dto import (
    AnnouncementDTO,
)
from src.app.transfer_objects.commands.announcement_cmd import (
    CreateAnnouncementDraftCMD,
    UpdateAnnouncementDraftCMD,
    PublishAnnouncementCMD,
)


class IAnnouncementService(ABC):
    """Service contract for announcement business logic"""

    @abstractmethod
    def create_draft(self, command: CreateAnnouncementDraftCMD) -> int:
        """Create a new announcement draft"""
        pass

    @abstractmethod
    def update_draft(self, command: UpdateAnnouncementDraftCMD) -> bool:
        """Update an existing announcement draft"""
        pass

    @abstractmethod
    def get_draft_by_id(self, announcement_id: int) -> Optional[AnnouncementDTO]:
        """Get announcement draft by ID"""
        pass

    @abstractmethod
    def get_drafts_by_creator(self, created_by_id: int) -> List[AnnouncementDTO]:
        """Get all drafts created by a specific user"""
        pass

    @abstractmethod
    def get_all_drafts(self) -> List[AnnouncementDTO]:
        """Get all announcement drafts"""
        pass

    @abstractmethod
    def publish_announcement(self, command: PublishAnnouncementCMD) -> bool:
        """Publish an announcement"""
        pass

    @abstractmethod
    def search_drafts(self, search: str) -> List[AnnouncementDTO]:
        """Search for announcement drafts by title or content"""
        pass

    @abstractmethod
    def delete_draft(self, announcement_id: int) -> bool:
        """Delete an announcement draft"""
        pass

    @abstractmethod
    def execute(
        self,
        search:Optional[str],
    ) -> List[AnnouncementDTO]:
        pass