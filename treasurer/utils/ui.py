STATUS_UI = {
    "FOR_TREASURER_REVIEW": {"label": "For Treasurer Review", "cls": "badge bg-warning-subtle text-warning-emphasis"},
    "PAID":                 {"label": "Paid",                 "cls": "badge bg-primary-subtle text-primary-emphasis"},
    "FOR_PRINTING":         {"label": "For Printing",         "cls": "badge bg-info-subtle text-info-emphasis"},
    "RELEASED":             {"label": "Released",             "cls": "badge bg-success-subtle text-success-emphasis"},
    "DECLINED":             {"label": "Declined",             "cls": "badge bg-danger-subtle text-danger-emphasis"},
}

ACTION_LABELS = {
    "REQUEST_CREATED":  "Request Created",
    "STATUS_CHANGED":   "Status Changed",
    "PAYMENT_ACCEPTED": "Payment Accepted",
    "LINE_ADDED":       "Item Added",
    "DECLINED":         "Declined",
}

def titleize(s: str | None) -> str:
    return "" if not s else s.replace("_", " ").title()
