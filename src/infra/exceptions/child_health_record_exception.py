from src.infra.exceptions.query_exec_exception import QueryExecutionException


class ChildHealthRecordException(QueryExecutionException):

    ERROR_CODES = {
        "P6010", "P6057", "P6067", "P6069", "P6076", "P6088",
        "P6089", "P6110", "P6111", "P6112", "P6120", "P6121", "P6122",
        "P6123", "P6187", "P6124", "P6125", "P6126", "P6127",
        "P6128", "P6129", "P6130", "P6131", "P6134", "P6135",
        "P6136", "P6137", "P6138", "P6139", "P6140", "P6143", "P6144",
        "P6233", "P6234", "P6235", "P6236", "P6237", "P6238", "P6239",
        "P6240", "P6242", "P6243", "P6244", "P6245", "P6246",
        "P6317",
        # custom error codes raised by add_child_visit_schedule stored procedure
        "P6145",  # scheduled date/time required
        "P6147",  # pending status not found
        "P6S06",  # (commented guard for duplicate exact datetime) keep for completeness
        "P6148"   # pending schedule already exists for this child on date
    }

    def __init__(self, message: str):
        self.message = message

    @classmethod
    def is_child_health_record_exception(cls, error_code: str) -> bool:
        return error_code in cls.ERROR_CODES
