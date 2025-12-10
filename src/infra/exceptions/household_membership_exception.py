from src.infra.exceptions.query_exec_exception import QueryExecutionException


class HouseholdMembershipException(QueryExecutionException):
    
    ERROR_CODES = {
        # custom error codes raised by household stored procedures
        "P6035",  # Failed to create a household
    }
    
    def __init__(self, message: str):
        self.message = message

    @classmethod
    def is_membership_exception(cls, error_code: str) -> bool:
        return error_code in cls.ERROR_CODES