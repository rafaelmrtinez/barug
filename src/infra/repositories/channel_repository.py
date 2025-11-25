from typing import List
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
from src.infra.contracts.connection_adapter import IConnectionAdapter


class ChannelRepository(IChannelRepository):
    """Concrete implementation of channel repository"""

    def __init__(self, ctx: IConnectionAdapter):
        self.ctx = ctx

    def upsert_announcement_channels(self, command: UpsertAnnouncementChannelsCMD) -> bool:
        """Upsert announcement channels using database function"""
        sql = "SELECT upsert_announcement_channels(%s, %s)"
        
        params = (command.announcement_id, command.channel_type_ids)
        result = self.ctx.execute_query(sql, params)
        return result is not None

    def get_announcement_channels(self, announcement_id: int) -> List[AnnouncementChannelDTO]:
        """Get channels for an announcement"""
        sql = """
            SELECT ac.announcement_channel_id, ac.announcement_id, ac.channel_type_id,
                   ac.priority, ac.is_enabled, ac.created_at, ac.updated_at,
                   ct.channel_type_name
            FROM public.announcement_channel ac
            LEFT JOIN public.channel_type ct ON ct.channel_type_id = ac.channel_type_id
            WHERE ac.announcement_id = %s
            ORDER BY ac.priority, ac.channel_type_id
        """
        
        result = self.ctx.execute_query(sql, (announcement_id,))
        return [
            AnnouncementChannelDTO(
                announcement_channel_id=row[0],
                announcement_id=row[1],
                channel_type_id=row[2],
                priority=row[3],
                is_enabled=row[4],
                created_at=row[5],
                updated_at=row[6],
                channel_type_name=row[7]
            )
            for row in result
        ]

    def create_announcement_recipients(self, command: CreateAnnouncementRecipientsCMD) -> int:
        """Create announcement recipients using database function"""
        sql = "SELECT create_announcement_recipients(%s)"
        
        result = self.ctx.execute_query(sql, (command.announcement_id,))
        return result[0][0] if result else 0

    def get_announcement_recipients(self, announcement_id: int) -> List[AnnouncementRecipientDTO]:
        """Get recipients for an announcement"""
        sql = """
            SELECT announcement_recipient_id, announcement_id, person_id,
                   channel_type_id, announcement_deliver_status_id,
                   created_at, delivered_at
            FROM public.announcement_recipient
            WHERE announcement_id = %s
            ORDER BY announcement_recipient_id
        """
        
        result = self.ctx.execute_query(sql, (announcement_id,))
        return [
            AnnouncementRecipientDTO(
                announcement_recipient_id=row[0],
                announcement_id=row[1],
                person_id=row[2],
                channel_type_id=row[3],
                announcement_deliver_status_id=row[4],
                created_at=row[5],
                delivered_at=row[6]
            )
            for row in result
        ]
    
    def choose_channel(self, announcement_id: int, person_id: int) -> List[int]:
        """Return list of channel_type_id using DB choose_channel function."""
        sql = "SELECT channel_type_id FROM choose_channel(%s, %s)"
        rows = self.ctx.execute_query(sql, (announcement_id, person_id))
        return [r[0] for r in rows] if rows else []