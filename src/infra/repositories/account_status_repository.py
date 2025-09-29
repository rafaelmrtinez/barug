from src.infra.database.connection_adapter import ConnectionAdapter


class AccountStatusRepository:
    
    def __init__(self, context: ConnectionAdapter):
        self.context = context
        
    def get_all(self):
        query = "SELECT * FROM request_status;"
        result = self.context.execute_query(query)
        return result