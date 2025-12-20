from src.infra.exceptions.query_exec_exception import QueryExecutionException


class PersonException(QueryExecutionException):
    
    ERROR_CODES = {
        'P6010',  # Person not found
        'P6112',  # Relationship to household head is invalid or not found
        'P6113',  # Relationship to family head is invalid or not found
        'P6114',  # This person is not found as active member
    }
    
    def __init__(self, message: str):
        self.message = message
        
    @staticmethod
    def is_person_exception(code: str) -> bool:
        return code in PersonException.ERROR_CODES