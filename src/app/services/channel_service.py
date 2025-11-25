from typing import List
from src.app.contracts.channel_service_contract import IChannelService
from src.domain.contracts.channel_repository_contract import IChannelRepository
from src.app.transfer_objects.dto.channel_dto import (
    ChannelTypeDTO,
    AnnouncementChannelDTO,
    AnnouncementRecipientDTO
)
from src.app.transfer_objects.commands.channel_cmd import (
    UpsertAnnouncementChannelsCMD,
    CreateAnnouncementRecipientsCMD
)


class ChannelService(IChannelService):
    """Service implementation for channel business logic"""

    def __init__(self, channel_repository: IChannelRepository):
        self.channel_repository = channel_repository

    def upsert_announcement_channels(self, command: UpsertAnnouncementChannelsCMD) -> bool:
        """Upsert channels for an announcement with validation"""
        if not command.announcement_id:
            raise ValueError("Announcement ID is required")
        
        if not command.channel_type_ids:
            raise ValueError("At least one channel type is required")
        
        return self.channel_repository.upsert_announcement_channels(command)

    def get_announcement_channels(self, announcement_id: int) -> List[AnnouncementChannelDTO]:
        """Get channels configured for an announcement"""
        if not announcement_id:
            raise ValueError("Announcement ID is required")
        
        return self.channel_repository.get_announcement_channels(announcement_id)

    def create_announcement_recipients(self, command: CreateAnnouncementRecipientsCMD) -> int:
        """Create recipients for an announcement with validation"""
        if not command.announcement_id:
            raise ValueError("Announcement ID is required")
        
        return self.channel_repository.create_announcement_recipients(command)

    def get_announcement_recipients(self, announcement_id: int) -> List[AnnouncementRecipientDTO]:
        """Get recipients for an announcement"""
        if not announcement_id:
            raise ValueError("Announcement ID is required")
        
        return self.channel_repository.get_announcement_recipients(announcement_id)

    def choose_channel(self, announcement_id: int, person_id: int) -> List[int]:
        """Choose channel for a person in an announcement"""
        if not announcement_id:
            raise ValueError("Announcement ID is required")
        if not person_id:
            raise ValueError("Person ID is required")
        
        return self.channel_repository.choose_channel(announcement_id, person_id)