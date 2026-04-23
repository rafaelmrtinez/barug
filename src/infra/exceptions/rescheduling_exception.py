from src.infra.exceptions.query_exec_exception import QueryExecutionException


class ReschedulingException(QueryExecutionException):
    
    ERROR_CODES = ["P5083", "P5085", "P5086", "P5093", "P6027", "P6028", "P6029", "P6030", "P5087"]
    
    def __init__(self, message: str):
        self.message = message
        
    @staticmethod
    def is_rescheduling_error() -> bool:
        return ReschedulingException.ERROR_CODES