
from supabase import Client
from dataclasses import dataclass


from src.infra.exceptions.general_infra_exception import InfrastructureException


@dataclass(frozen=True)
class SupabaseAdapter:
    
    client: Client
    
    def get_client(self) -> Client:
        """
        Returns the Supabase client instance.
        """
        try:
            
            if not self.client:
                raise InfrastructureException("Supabase client is not initialized.")
            return self.client
        except Exception as e:
            raise InfrastructureException(f"Failed to get Supabase client: {e}")