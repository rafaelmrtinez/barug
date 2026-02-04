from dataclasses import dataclass
from typing import Optional


@dataclass
class ChannelTypeDTO:
    """DTO for channel type"""
    channel_type_id: int
    channel_type_name: str


@dataclass
class AnnouncementChannelDTO:
    """DTO for announcement channel"""
    announcement_channel_id: int
    announcement_id: int
    channel_type_id: int
    priority: int
    is_enabled: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    channel_type_name: Optional[str] = None


@dataclass
class AnnouncementRecipientDTO:
    """DTO for announcement recipient"""
    announcement_recipient_id: int
    announcement_id: int
    person_id: int
    channel_type_id: int
    announcement_deliver_status_id: int
    created_at: Optional[str] = None
    delivered_at: Optional[str] = None