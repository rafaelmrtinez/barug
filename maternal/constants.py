BMI_CHOICES = (
    (1, "Low"),
    (2, "Normal"),
    (3, "High"),
)

# FORM FOR CHILD VISIT
# Choices
AGE_GROUPS = (
    ("10-14", "10–14"),
    ("15-19", "15–19"),
    ("20-49", "20–49"),
)

OUTCOME_CHOICES = (
    ("fullterm", "Fullterm"),
    ("preterm", "Preterm"),
)

DELIVERY_TYPE_CHOICES = (
    ("nsvd", "NSVD"),
    ("cs", "CS"),
)

GENDER_CHOICES = (
    ("female", "Female"),
    ("male", "Male"),
)

SYMPTOM_CHOICES = [
    ("increased_bp", "Increased BP"),
    ("epigastric_pain", "Epigastric pain"),
    ("nausea_vomiting", "Nausea/Vomiting"),
    ("blurred_vision", "Blurring of vision"),
    ("edema", "Edema"),
    ("severe_headache", "Severe headache"),
    ("abnormal_discharge", "Abnormal vaginal discharges"),
    ("vaginal_bleeding", "Vaginal bleeding"),
    ("chills_fever", "Chills & fever"),
    ("diff_breathing", "Difficulty in breathing"),
    ("varicosities", "Varicosities"),
    ("abdominal_pain", "Abdominal pain"),
]

SEX_CHOICES = [('M', 'Male'), ('F', 'Female')]

PLACE_OF_DELIVERY_CHOICES = [
    ('1', 'HOSPITAL (GOVERNMENT)'),
    ('2', 'HOSPITAL (PRIVATE)'),
    ('3', 'HOME'),
    ('4', 'PRIVATE CLINIC'),
    ('5', 'LYING-IN CLINIC'),
    ('6', 'HEALTH CENTER'),
]

PLACE_OF_DELIVERY_MAP = {
    'HOSPITAL (PRIVATE)': 'hospital',
    'HOSPITAL (PUBLIC)': 'hospital',
    'HOSPITAL': 'hospital',
    'HOME': 'home',
    'PRIVATE CLINIC': 'private_clinic',
    'LYING IN': 'lying_in',
    'LYING-IN': 'lying_in',
    'HC': 'hc',
    'HEALTH CENTER': 'hc',
}


IMMUNIZATION_TYPES = [
    ('bcg', 'BCG'),
    ('hepbv', 'Hep. BV'),
    ('pcv', 'PCV'),
    ('opv', 'OPV'),
    ('amv', 'AMV'),
    ('pentavalent', 'Pentavalent'),
]