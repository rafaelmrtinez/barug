# verification/constants.py

# Map your doc_type_id (from DB) to the internal OCR key.
# Make sure these IDs match your lookup table.

DOC_TYPE_KEY_BY_ID = {
    1: "philippine_passport",
    2: "philippine_national_id",
    3: "sss_umid",
    4: "gsis_ecard",
    5: "prc_id",
    6: "drivers_license",
    7: "philhealth_id",
    8: "voters_id",
    9: "postal_id",
    10: "senior_citizen_id",
    11: "pwd_id",
    12: "owwa_id",
    13: "ibp_id",
    14: "tin_id",
    15: "birth_certificate",
    16: "barangay_certificate",
    17: "school_id",
    18: "resident_picture",
    19: "resident_selfie",
}

DOCUMENT_KEYWORDS = {
    "philippine_passport": ["passport", "republic of the philippines", "department of foreign affairs", "dfa", "passport no"],
    "philippine_national_id": ["philippine identification", "philsys", "philid", "republic of the philippines", "psn", "ephilid"],
    "sss_umid": ["sss", "social security", "unified multi purpose id", "umid"],
    "gsis_ecard": ["gsis", "government service insurance", "ecard"],
    "prc_id": ["professional regulation commission", "prc", "professional identification card"],
    "drivers_license": ["land transportation office", "lto", "driver", "license", "dl no"],
    "philhealth_id": ["philhealth", "philhealth identification card"],
    "voters_id": ["commission on elections", "comelec", "voter"],
    "postal_id": ["postal", "phlpost", "philippine postal corporation"],
    "barangay_certificate": ["barangay", "certificate", "clearance", "certificate of residency"],
    "senior_citizen_id": ["senior citizen", "osca", "office for senior citizens affairs"],
    "pwd_id": ["person with disability", "pwd", "persons with disability affairs"],
    "owwa_id": ["owwa", "overseas workers welfare administration"],
    "ibp_id": ["integrated bar of the philippines", "ibp"],
    "tin_id": ["tax identification", "tin", "bureau of internal revenue", "bir"],
    "birth_certificate": ["philippine statistics authority", "psa", "certificate of live birth", "civil registrar"],
    "school_id": ["school", "student", "university", "college", "senior high", "lrn", "department of education", "deped"],
    # "resident_picture": [],
    # "resident_selfie": [],
}