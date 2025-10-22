class MaternalHealthRecordException(Exception):
    """Base exception for maternal module."""

    ERROR_CODES = {
        "P6057",
        "P6010",
        "P6059",
        "P6060",
        "P6114",
        "P6160",
        "P6161",
        "P6162",
        "P6163",
        "P6164",
    }

    def __init__(self, message):
        self.message = message

    @classmethod
    def is_maternal_health_record_exception(cls, error_code: str) -> bool:
        print(f"Checking if error code {error_code} is a maternal health record exception.")
        return error_code in cls.ERROR_CODES
