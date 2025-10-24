class MaternalHealthRecordException(Exception):
    """Base exception for maternal module."""

    ERROR_CODES = {
        "P6010",
        "P6057",
        "P6059",
        "P6060",
        "P6114",
        "P6160",
        "P6161",
        "P6162",
        "P6163",
        "P6164",
        "P6176",
        "P6177",
        "P6178",
        "P6179",
        "P6180",
        "P6186",
        # codes found in the TT insertion SQL
        "P6187",
        "P6188",
        "P6189",
        "P6190",
        "P6191",
        "P6192",
        "P6193",
        "P6194",
        "P6195",
        "P6196",
    }

    def __init__(self, message):
        self.message = message

    @classmethod
    def is_maternal_health_record_exception(cls, error_code: str) -> bool:
        print(
            f"Checking if error code {error_code} is a maternal health record exception.")
        return error_code in cls.ERROR_CODES
