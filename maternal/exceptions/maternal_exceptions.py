class MaternalHealthRecordException(Exception):
    """Base exception for maternal module."""

    ERROR_CODES = {
        # general / existing codes
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
        # codes from maternal checklist function
        "P6201",
        "P6202",
        "P6203",
        "P6204",
        "P6205",
        # codes from micronutrients function (added)
        "P6181",  # Iron end date cannot be in the future.
        "P6182",  # Deworming date cannot be in the future.
        "P6183",  # Iron end date cannot be before start date.
        # codes from present_pregnancy_status function (added)
        "P6265",  # Gravida cannot be negative.
        "P6266",  # Para cannot be negative.
        "P6267",  # Para cannot exceed Gravida.
        "P6268",  # LMP date cannot be in the future.
        "P6269",  # EDD cannot be before LMP.
        "P6270",  # Full-term and preterm cannot both be TRUE.
        # codes from present_pregnancy_status overlay/checks
        "P6271",  # Para cannot exceed Gravida (after overlay).
        "P6272",  # EDD cannot be before LMP (after overlay).
        "P6273",  # Full-term and preterm cannot both be TRUE (after overlay).
        "P6274",  # Only one present pregnancy status allowed per ANC visit.
    }

    def __init__(self, message):
        self.message = message

    @classmethod
    def is_maternal_health_record_exception(cls, error_code: str) -> bool:
        print(
            f"Checking if error code {error_code} is a maternal health record exception.")
        return error_code in cls.ERROR_CODES
