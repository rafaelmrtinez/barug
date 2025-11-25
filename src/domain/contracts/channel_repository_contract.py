from abc import ABC, abstractmethod
from typing import List
from src.app.transfer_objects.dto.channel_dto import (
    ChannelTypeDTO,
    AnnouncementChannelDTO,
    AnnouncementRecipientDTO
)
from src.app.transfer_objects.commands.channel_cmd import (
    UpsertAnnouncementChannelsCMD,
    CreateAnnouncementRecipientsCMD
)


class IChannelRepository(ABC):
    """Contract for channel repository"""

    @abstractmethod
    def upsert_announcement_channels(self, command: UpsertAnnouncementChannelsCMD) -> bool:
        """Upsert announcement channels"""
        pass

    @abstractmethod
    def get_announcement_channels(self, announcement_id: int) -> List[AnnouncementChannelDTO]:
        """Get channels for an announcement"""
        pass

    @abstractmethod
    def create_announcement_recipients(self, command: CreateAnnouncementRecipientsCMD) -> int:
        """Create announcement recipients and return count"""
        pass

    @abstractmethod
    def get_announcement_recipients(self, announcement_id: int) -> List[AnnouncementRecipientDTO]:
        """Get recipients for an announcement"""
        pass

    @abstractmethod
    def choose_channel(self, announcement_id: int, person_id: int) -> List[int]:
        """Choose channel for a person in an announcement"""
        pass