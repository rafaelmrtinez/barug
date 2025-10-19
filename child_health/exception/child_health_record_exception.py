from src.infra.exceptions.query_exec_exception import QueryExecutionException


class ChildHealthRecordException(QueryExecutionException):
    
    ERROR_CODES = {"P6057", "P6010", "P6110", "P6067", "P6069", "P6111", "P6112", 'P6122', 'P6132', 'P6133', 'P6134', 'P6123', 'P6124', 'P6125', 'P6126', 'P6135', 'P6127', 'P6136', 'P6137', 'P6138', 'P6139'}

    
    def __init__(self, message: str):
        self.message = message
        
    @classmethod
    def is_child_health_record_exception(cls, error_code: str) -> bool:
        return error_code in cls.ERROR_CODES