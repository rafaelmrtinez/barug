from src.infra.exceptions.query_exec_exception import QueryExecutionException


class HouseholdUpdateException(QueryExecutionException):

    ERROR_CODES = {
        'P6039': 'Relationship "FAMILY HEAD" not configured in relationship table.',
        'P6042': 'Household not found.',
        'P6047': 'House type does not exist.',
        'P6048': 'House ownership type does not exist.',
        'P6050': 'Family income does not exist.',
        'P6051': 'NHTS status does not exist.',
        'P6052': 'Indigent status does not exist.',
        'P6053': 'Family type does not exist.',
        'P6054': 'Household does not exist.',
        'P6055': 'Family head does not exist.',
        'P6056': 'Relationship to household head does not exist in relationship.',
        'P6118': 'Reason is required or new family head not found.',
        'P6120': 'New head must be an active member of this family or is already the family head.',
        'P6043': 'Family not found.',
    }

    def __init__(self, message: str):
        self.message = message

    @classmethod
    def is_household_update_exception(cls, error_code: str) -> bool:
        return error_code in cls.ERROR_CODES