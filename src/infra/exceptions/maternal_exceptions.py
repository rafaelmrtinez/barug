from src.infra.exceptions.query_exec_exception import QueryExecutionException


class MaternalException(QueryExecutionException):
    
    ERROR_CODES = [
        "P6057", "P6010", "P6067", "P6068", "P6058", "P6069"
    ]
    
    def __init__(self, message: str):
        self.message = message
        
    @classmethod
    def is_maternal_exception(cls, code: int) -> bool:
        return code in cls.ERROR_CODES