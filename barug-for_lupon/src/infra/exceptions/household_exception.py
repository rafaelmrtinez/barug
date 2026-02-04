from src.infra.exceptions.query_exec_exception import QueryExecutionException



class HouseholdException(QueryExecutionException):

    ERROR_CODES = {
        'P6885',  # family id is required, family does not exist
        'P6886',  # staff id is required, staff does not exist
        'P6887',  # family has active house member(s) with PENDING residential status
        'P6888',  # family is already marked as quarterly visited
        'P6889',  # household id is required, household does not exist
        'P6890',  # household has family units not yet visited
        'P6891',  # household already marked as quarterly visited
        'P6892',  # user type STAFF not configured
        'P6893',  # log subsystem HOUSEHOLD PROFILING not configured
        'P6899',  # unexpected error in mark_household_quarterly_visited or mark_family_quarterly_visited
    }

    def __init__(self, message: str):
        self.message = message

    @classmethod
    def is_household_exception(cls, error_code: str) -> bool:
        return error_code in cls.ERROR_CODES