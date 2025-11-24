from abc import ABC, abstractmethod
from typing import List, Tuple
from src.app.transfer_objects.dto.audience_dto import (
    AudienceDTO,
    AudienceScopeDTO,
    AudiencePersonDTO,
)
from src.app.transfer_objects.commands.audience_cmd import (
    AddAnnouncementAudienceCMD,
)


class IAudienceService(ABC):
    """Service contract for announcement audience business logic"""

    @abstractmethod
    def add_announcement_audience(self, command: AddAnnouncementAudienceCMD) -> Tuple[int, int]:
        """Add audience to announcement with validation"""
        pass

    @abstractmethod
    def get_audience_scopes(self) -> List[AudienceScopeDTO]:
        """Get all available audience scopes"""
        pass

    @abstractmethod
    def get_announcement_audiences(self, announcement_id: int) -> List[AudienceDTO]:
        """Get all audiences for an announcement"""
        pass

    @abstractmethod
    def get_audience_persons(self, audience_id: int) -> List[AudiencePersonDTO]:
        """Get all persons in an audience"""
        pass