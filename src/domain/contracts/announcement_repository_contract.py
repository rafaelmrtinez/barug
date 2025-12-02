from abc import ABC, abstractmethod
from typing import List, Optional
from src.app.transfer_objects.dto.announcement_dto import (
    AnnouncementDTO,
    AnnouncementStatusDTO,
)
from src.app.transfer_objects.dto.publish_result_dto import PublishResultDTO
from src.app.transfer_objects.commands.announcement_cmd import (
    CreateAnnouncementDraftCMD,
    UpdateAnnouncementDraftCMD,
    PublishAnnouncementCMD,
)
from src.app.transfer_objects.commands.publish_now_cmd import PublishAnnouncementNowCMD
from src.app.transfer_objects.commands.schedule_cmd import ScheduleAnnouncementCMD


class IAnnouncementRepository(ABC):
    """Repository contract for announcement operations"""

    @abstractmethod
    def create_draft(self, command: CreateAnnouncementDraftCMD) -> int:
        """Create a new announcement draft and return the ID"""
        pass

    @abstractmethod
    def update_draft(self, command: UpdateAnnouncementDraftCMD) -> bool:
        """Update an existing announcement draft"""
        pass

    @abstractmethod
    def get_by_id(self, announcement_id: int) -> Optional[AnnouncementDTO]:
        """Get announcement by ID"""
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
    def publish_announcement(self, announcement_id: int, published_by_id: int) -> bool:
        """Publish an announcement"""
        pass
    
    @abstractmethod
    def publish_announcement_now(self, command: PublishAnnouncementNowCMD) -> PublishResultDTO:
        """Publish an announcement immediately using the database function"""
        pass
    
    @abstractmethod
    def schedule_announcement(self, command: ScheduleAnnouncementCMD):
        """Schedule an announcement for future publishing"""
        pass

    @abstractmethod
    def get_announcement_statuses(self) -> List[AnnouncementStatusDTO]:
        """Get all announcement statuses"""
        pass

    @abstractmethod
    def search_drafts(self, search: str) -> List[AnnouncementDTO]:
        """Search for announcement drafts based on a search term"""
        pass

    @abstractmethod
    def delete_draft(self, announcement_id: int) -> bool:
        """Delete an announcement draft"""
        pass

    @abstractmethod
    def cancel_scheduled(self, announcement_id: int) -> bool:
        """Cancel a scheduled announcement"""
        pass