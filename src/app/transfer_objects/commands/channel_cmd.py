from dataclasses import dataclass
from typing import List, Optional


@dataclass
class UpsertAnnouncementChannelsCMD:
    """Command for upserting announcement channels"""
    announcement_id: int
    channel_type_ids: List[int]


@dataclass
class CreateAnnouncementRecipientsCMD:
    """Command for creating announcement recipients"""
    announcement_id: int