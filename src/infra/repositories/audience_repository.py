from typing import List, Tuple
from src.domain.contracts.audience_repository_contract import IAudienceRepository
from src.app.transfer_objects.dto.audience_dto import (
    AudienceDTO,
    AudienceScopeDTO,
    AudiencePersonDTO
)
from src.app.transfer_objects.commands.audience_cmd import (
    AddAnnouncementAudienceCMD,
)
from src.infra.contracts.connection_adapter import IConnectionAdapter


class AudienceRepository(IAudienceRepository):
    """Concrete implementation of audience repository"""

    def __init__(self, ctx: IConnectionAdapter):
        self.ctx = ctx

    def add_announcement_audience(self, command: AddAnnouncementAudienceCMD) -> Tuple[int, int]:
        """Add audience to announcement using the database function"""
        sql = """
            SELECT audience_id, inserted_persons
            FROM add_announcement_audience(%s, %s, %s, %s, %s)
        """
        
        params = (
            command.announcement_id,
            command.audience_scope_id,
            command.role_id,
            command.purok_sitio_id,
            command.person_ids
        )
        
        result = self.ctx.execute_query(sql, params)
        if result:
            return (result[0][0], result[0][1])
        return (0, 0)

    def get_audience_scopes(self) -> List[AudienceScopeDTO]:
        """Get all audience scopes"""
        sql = """
            SELECT audience_scope_id, audience_scope_name
            FROM public.audience_scope
            ORDER BY audience_scope_id
        """
        
        result = self.ctx.execute_query(sql)
        return [
            AudienceScopeDTO(
                audience_scope_id=row[0],
                audience_scope_name=row[1]
            )
            for row in result
        ]

    def get_announcement_audiences(self, announcement_id: int) -> List[AudienceDTO]:
        """Get all audiences for an announcement"""
        sql = """
            SELECT a.audience_id, a.announcement_id, a.audience_scope_id,
                   a.role_id, a.purok_sitio_id, aus.audience_scope_name,
                   r.role_name, ps.purok_sitio_name,
                   (SELECT COUNT(*) FROM public.audience_person_list apl WHERE apl.audience_id = a.audience_id) as inserted_persons
            FROM public.audience a
            LEFT JOIN public.audience_scope aus ON aus.audience_scope_id = a.audience_scope_id
            LEFT JOIN public.rolee r ON r.role_id = a.role_id
            LEFT JOIN public.purok_sitio ps ON ps.purok_sitio_id = a.purok_sitio_id
            WHERE a.announcement_id = %s
            ORDER BY a.audience_id
        """
        
        result = self.ctx.execute_query(sql, (announcement_id,))
        return [
            AudienceDTO(
                audience_id=row[0],
                announcement_id=row[1],
                audience_scope_id=row[2],
                role_id=row[3],
                purok_sitio_id=row[4],
                audience_scope_name=row[5],
                role_name=row[6],
                purok_sitio_name=row[7],
                inserted_persons=row[8]
            )
            for row in result
        ]

    def get_audience_persons(self, audience_id: int) -> List[AudiencePersonDTO]:
        """Get all persons in an audience"""
        sql = """
            SELECT audience_person_list_id, audience_id, person_id
            FROM public.audience_person_list
            WHERE audience_id = %s
            ORDER BY audience_person_list_id
        """
        
        result = self.ctx.execute_query(sql, (audience_id,))
        return [
            AudiencePersonDTO(
                audience_person_list_id=row[0],
                audience_id=row[1],
                person_id=row[2]
            )
            for row in result
        ]