from src.infra.exceptions.query_exec_exception import QueryExecutionException


class HouseholdUpdateException(QueryExecutionException):

    ERROR_CODES = {
        'P6042': 'Household not found.',
        'P6043': 'Family not found.',
        'P6047': 'House type does not exist.',
        'P6048': 'House ownership type does not exist.',
        'P6118': 'Reason is required or new family head not found.',
        'P6120': 'New head must be an active member of this family or is already the family head.'
    }

    def __init__(self, message: str):
        self.message = message

    @classmethod
    def is_household_update_exception(cls, error_code: str) -> bool:
        return error_code in cls.ERROR_CODES