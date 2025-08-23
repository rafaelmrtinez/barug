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
    
    def find_resident_family_unit_if_exist(self, id):
        result = (
            self.client.table('house_member').select(count='exact').eq('person_id', id).execute()
        )
        return True if result.count else False