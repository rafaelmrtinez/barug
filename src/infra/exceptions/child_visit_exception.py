from src.infra.exceptions.query_exec_exception import QueryExecutionException


class ChildVisitException(QueryExecutionException):

    ERROR_CODES = [
        "P6057", "P6076", "P6077",
        "P6078", "P6079", "P6080",
        "P6081", "P6082", "P6083",
        "P6084", "P6085", "P6086",
        "P6087", "P6088", "P6089",
        "P6090"
    ]
    
    def __init__(self, message: str):
        self.message = message
        
    @classmethod
    def is_child_visit_exception(cls, code: int) -> bool:
        return code in cls.ERROR_CODES
