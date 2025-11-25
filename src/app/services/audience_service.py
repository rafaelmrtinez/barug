from typing import List, Tuple
from src.app.contracts.audience_service_contract import IAudienceService
from src.domain.contracts.audience_repository_contract import IAudienceRepository
from src.app.transfer_objects.dto.audience_dto import (
    AudienceDTO,
    AudienceScopeDTO,
    AudiencePersonDTO
)
from src.app.transfer_objects.commands.audience_cmd import (
    AddAnnouncementAudienceCMD,
)


class AudienceService(IAudienceService):
    """Service implementation for announcement audience business logic"""

    def __init__(self, audience_repository: IAudienceRepository):
        self.audience_repository = audience_repository

    def add_announcement_audience(self, command: AddAnnouncementAudienceCMD) -> Tuple[int, int]:
        """Add audience to announcement with validation"""
        if not command.announcement_id:
            raise ValueError("Announcement ID is required")
        
        if not command.audience_scope_id:
            raise ValueError("Audience scope ID is required")
        
        # Validate scope-specific requirements
        if command.audience_scope_id == 3 and not command.role_id:  # Staff scope
            raise ValueError("Role ID is required for staff scope")
        
        if command.audience_scope_id in [4, 5, 8] and not command.purok_sitio_id:  # Household/Family/Purok scopes
            raise ValueError("Purok/Sitio ID is required for this scope")
        
        if command.audience_scope_id == 6 and not command.person_ids:  # Specific persons
            raise ValueError("Person IDs are required for specific persons scope")
        
        return self.audience_repository.add_announcement_audience(command)

    def get_audience_scopes(self) -> List[AudienceScopeDTO]:
        """Get all available audience scopes"""
        return self.audience_repository.get_audience_scopes()

    def get_announcement_audiences(self, announcement_id: int) -> List[AudienceDTO]:
        """Get all audiences for an announcement"""
        if not announcement_id:
            raise ValueError("Announcement ID is required")
        
        return self.audience_repository.get_announcement_audiences(announcement_id)

    def get_audience_persons(self, audience_id: int) -> List[AudiencePersonDTO]:
        """Get all persons in an audience"""
        if not audience_id:
            raise ValueError("Audience ID is required")
        
        return self.audience_repository.get_audience_persons(audience_id)