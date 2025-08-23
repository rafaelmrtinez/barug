from src.infra.adapter.supabase_adapter import SupabaseAdapter


class FamilyCreationRepository:
    
    def __init__(self, client: SupabaseAdapter):
        self.client = client.client
        
    def create_family_unit(self, data):
        func = 'insert_family_creation_request'
        result = (
            self.client.rpc(fn=func, params=data).execute()
        )
        
        return result.data