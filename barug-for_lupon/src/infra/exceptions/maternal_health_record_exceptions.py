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
        # codes from previous_pregnancy_info function (added)
        "P6172",  # Delivery type not found.
        "P6173",  # Sex not found.
        "P6174",  # APGAR score must be between 0 and 10.
        "P6175",  # Delivery date cannot be in the future.
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
        # codes from maternal lab result insertion function
        "P6197",  # Each array element must be an object with required keys
        "P6198",  # Date tested missing or in the future
        "P6199",  # Invalid lab test type
        "P6207",  # Lab test type id not found
        "P6208",  # Duplicate lab entry in same request
        "P6209",  # Duplicate lab entry already exists in DB for that date
        # Result image path required / cannot be empty (commented rules)
        "P6275",
        "P6276",  # Result image path array entries must be non-empty strings
        "P6277",  # Result image path must be string or array
        # codes from maternal ANC visit/row insertion function
        "P6165",  # AOG weeks must be between 0 and 45
        "P6166",  # AOG days must be between 0 and 6
        "P6167",  # BP systolic out of valid range
        "P6168",  # BP diastolic out of valid range
        "P6169",  # Record status ONGOING not found
        "P6170",  # Trimester stage lookup not found
        "P6171",  # ANC record for today's visit already exists
        # codes from insert_risk_codes SQL function (added)
        "P6210",  # Provide a non-empty JSON array of risk category id integers
        "P6211",  # All risk_category_id values must be integers
        "P6212",  # Invalid risk category id
        "P6213",  # Risk category id not found
        "P6214",  # Duplicate risk category in the same request
        "P6215",  # Risk category already recorded for this maternal record
        # codes from ANC findings/notes update function
        # Only authorized staff (midwife/nurse) may update findings/notes
        "P6216",
        "P6217",  # ANC record for this visit was not found
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
        # codes from set_maternal_record_status SQL function
        "P6229",  # Missing required params (staff id/status)
        "P6230",  # Invalid status id
        "P6231",  # Status not allowed (only COMPLETE/INCOMPLETE)
        "P6232",  # Required ANC visits not met for COMPLETE
        # codes from complete_maternal_visit_and_schedule SQL function
        "P6221",  # Maternal health record id is required
        "P6222",  # Visit COMPLETE status not found
        "P6223",  # Schedule statuses PENDING/COMPLETED not found
        # codes from scheduling SQL functions (prenatal/postpartum)
        "P6218",  # Scheduled date/time required or PENDING status missing
        "P6219",  # Duplicate exact date+time schedule (commented guard)
        "P6220",  # Pending schedule exists for this maternal record on date
        "P6M05",  # Provided status id does not exist (note: as-seen in SQL)
        "P6256",  # Postpartum record not found for maternal record
    "P6255",  # Postpartum record for today's visit not found
    "P6124",  # Feeding type not found
        "P6257",  # Scheduled date/time required (postpartum)
        "P6258",  # Pending postpartum schedule already exists on date
        "P6147",  # Pending status not found (postpartum)
        # codes introduced by insert_postpartum_record SQL function
        "P6247",  # Postpartum record already exists for this maternal record
        "P6248",  # Attended-by staff not found
        "P6249",  # Place of delivery type not found
        "P6250",  # Pads per day baseline cannot be negative
        "P6251",  # Time of delivery provided without a delivery date
        "P6252",  # Date of delivery cannot be in the future
        "P6253",  # Time of delivery cannot be in the future
        "P6254",  # BF initiation time cannot be in the future
    }

    def __init__(self, message):
        self.message = message

    @classmethod
    def is_maternal_health_record_exception(cls, error_code: str) -> bool:
        print(
            f"Checking if error code {error_code} is a maternal health record exception.")
        return error_code in cls.ERROR_CODES
