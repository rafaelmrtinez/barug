# lupon_pres/constants.py
"""
Constants for lupon_pres - mirrors lupon_mem.constants
"""

# KP Forms catalog for static chooser
KP_FORMS_CATALOG = [
    {"code": "KP-7", "name": "Complaint Form"},
    {"code": "KP-8", "name": "Notice of Hearing (Mediation)"},
    {"code": "KP-9", "name": "Summons for Respondent"},
    {"code": "KP-10", "name": "Notice for Constitution of Pangkat"},
    {"code": "KP-11", "name": "Notice to Chosen Pangkat Member"},
    {"code": "KP-12", "name": "Notice of Hearing (Conciliation)"},
    {"code": "KP-13", "name": "Subpoena"},
    {"code": "KP-14", "name": "Agreement for Arbitration"},
    {"code": "KP-15", "name": "Arbitration Award"},
    {"code": "KP-16", "name": "Amicable Settlement"},
    {"code": "KP-17", "name": "Repudiation"},
    {"code": "KP-18", "name": "Notice of Hearing (Enforcement)"},
    {"code": "KP-19", "name": "Failure to Appear"},
    {"code": "KP-20", "name": "Certification to File Action"},
    {"code": "KP-20A", "name": "CFA (Mediation)"},
    {"code": "KP-20B", "name": "CFA (Conciliation)"},
    {"code": "KP-21", "name": "Notice of Execution"},
    {"code": "KP-22", "name": "Notice to Vacate"},
    {"code": "KP-23", "name": "Notice of Garnishment"},
    {"code": "KP-24", "name": "Satisfaction of Judgment"},
    {"code": "KP-25", "name": "Certificate of Settlement"},
    {"code": "MED-ATT-2025", "name": "Mediation Attendance"},
]

# Form status options
FORM_STATUS_CHOICES = [
    ("DRAFT", "Draft"),
    ("SUBMITTED", "Submitted"),
    ("APPROVED", "Approved"),
    ("REJECTED", "Rejected"),
]

# Case status options
CASE_STATUS_CHOICES = [
    ("OPEN", "Open"),
    ("CLOSED", "Closed"),
    ("PENDING", "Pending"),
]

# Settlement status options
SETTLEMENT_STATUS_CHOICES = [
    ("SETTLED", "Settled"),
    ("NOT SETTLED", "Not Settled"),
    ("PENDING", "Pending"),
    ("ARBITRATED", "Arbitrated"),
]