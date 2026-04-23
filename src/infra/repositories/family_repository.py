from src.domain.contracts.family_repository import IFamilyRepository
from src.infra.contracts.connection_adapter import IConnectionAdapter


class FamilyRepository(IFamilyRepository):
    
    def __init__(self, ctx: IConnectionAdapter):
        self.ctx = ctx
        
    def get_family_id_by_family_no(self, family_no: str) -> int | None:
        cmd = """
        SELECT family_id AS p_family_id FROM family_unit WHERE family_num = %s;
        """
        row = self.ctx.execute_query_to_dict(cmd, [family_no])
        
        if not row:
            return None
        
        return row[0]["p_family_id"]