from src.infra.exceptions.query_exec_exception import QueryExecutionException


class ChildHealthRecordExcetion(QueryExecutionException):
    
    ERROR_CODES = {"P6057", "P6010", "P6110", "P6067", "P6069", "P6111", "P6112"}

    
    def __init__(self, message: str):
        self.message = message
        
    @classmethod
    def is_child_health_record_exception(cls, error_code: str) -> bool:
        return error_code in cls.ERROR_CODES