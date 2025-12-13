from src.infra.exceptions.query_exec_exception import QueryExecutionException


class HouseholdUpdateException(QueryExecutionException):

    ERROR_CODES = {
        'P6042': 'Household not found.',
        'P6047': 'House type does not exist.',
        'P6048': 'House ownership type does not exist.'
    }

    def __init__(self, message: str):
        self.message = message

    @classmethod
    def is_household_update_exception(cls, error_code: str) -> bool:
        return error_code in cls.ERROR_CODES