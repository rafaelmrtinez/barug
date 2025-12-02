from src.infra.contracts.connection_adapter import IConnectionAdapter


class ChildHealthRecordCommands:
    
    def __init__(self, connection: IConnectionAdapter):
        self._connection = connection