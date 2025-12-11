from src.infra.exceptions.query_exec_exception import QueryExecutionException


class MembershipException(QueryExecutionException):

    ERROR_CODES = {
        # custom error codes raised by household/family stored procedures
        "P6035",  # Failed to create a household
        "P6036",  # Household ID does not exist
        "P6037",  # Family head must be a registered person
        "P6038",  # Provided relationship to household head does not exist
        "P6039",  # Relationship "FAMILY HEAD" not configured in relationship table
        "P5009",  # Failed to create a family unit
        "P5010",
    }

    def __init__(self, message: str):
        self.message = message

    @classmethod
    def is_membership_exception(cls, error_code: str) -> bool:
        return error_code in cls.ERROR_CODES