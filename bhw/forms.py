from django import forms
from datetime import datetime

HOUSE_OWNERSHIP_CHOICES = [
    ("", "— All ownerships —"),
    (1, "OWNED"),
    (2, "RENTED"),
    (3, "FAMILY-OWNED"),
    (4, "GOVERNMENT HOUSING"),
    (5, "INFORMAL SETTLER"),
]

HOUSE_TYPE_CHOICES = [
    ("", "— All types —"),
    (1, "CONCRETE"),
    (2, "SEMI-CONCRETE"),
    (3, "LIGHT MATERIAL"),
]

PUROK_SITIO_CHOICES = [
    ("", "— Select Purok/Sitio —"),
    (1, "Kanipaan"),
    (2, "Pampango"),
    (3, "Lutaw-Lutaw"),
    (4, "Mauco"),
]

HOUSEHOLD_TYPE_CHOICES = [
    ("", "— All household types —"),
    (1, "NUCLEAR FAMILY"),
    (2, "EXTENDED FAMILY"),
    (3, "BOARDING HOUSE"),
    (4, "SHARED APARTMENT"),
    (5, "SOLO HOUSEHOLD"),
    (6, "GOVERNMENT HOUSING"),
    (7, "INFORMAL SETTLER"),
]

NHTS_STATUS_CHOICES = [
    ("", "— All NHTS status —"),
    (1, "NHTS MEMBER"),
    (2, "NOT NHTS MEMBER"),
]

INDIGENT_STATUS_CHOICES = [
    ("", "— All indigent status —"),
    (1, "INDIGENT"),
    (2, "NOT INDIGENT"),
]

BMI_CHOICES = (
    (1, "Low"),
    (2, "Normal"),
    (3, "High"),
)

class ChildHealtheRecordForm(forms.Form):
    """VALIDATION TO BE IMPLEMENTED IN BHW add_child VIEW"""
    child_id = forms.CharField(max_length=20, required=True, error_messages={'required': 'Child full name is required.'})
    mother_id = forms.IntegerField(required=True, error_messages={'required': 'Mother full name is required.'})
    father_id = forms.IntegerField(required=False, error_messages={'required': 'Father full name is required.'})
    birth_order = forms.CharField(max_length=50, required=True, error_messages={'required': 'Birth order is required.'})
    delivery_place_type_id = forms.IntegerField(required=True, error_messages={'required': 'Delivery place is required.'})
    family_id = forms.CharField(max_length=20, required=True, error_messages={'required': 'Family number is required.'})

class MaternalBhwIntakeForm(forms.Form):
    # Required
    person_id   = forms.IntegerField(widget=forms.HiddenInput())
    husband_id  = forms.IntegerField(required=False, widget=forms.HiddenInput())
    family_id = forms.IntegerField(label="Family ID", required=False)

    # Anthropometrics
    weight = forms.DecimalField(label="Weight (kg)", required=False, min_value=0, decimal_places=2)
    height = forms.DecimalField(label="Height (cm)", required=False, min_value=0, decimal_places=2)
    bmi_status_id = forms.ChoiceField(label="BMI Status", choices=BMI_CHOICES, required=False)

    # Plans
    place_of_delivery_plan = forms.CharField(label="Planned Place of Delivery", required=False)
    newborn_screening_plan = forms.BooleanField(label="Newborn screening planned?", required=False)

    # Past medical/obstetric history
    prev_illness = forms.CharField(widget=forms.Textarea, required=False, label="Previous illness")
    prev_hospitalization = forms.CharField(widget=forms.Textarea, required=False, label="Previous hospitalization")
    prev_preg_complication = forms.CharField(widget=forms.Textarea, required=False, label="Previous pregnancy complications")

    num_children_born_alive = forms.IntegerField(required=False, min_value=0, label="# children born alive")
    num_children_living = forms.IntegerField(required=False, min_value=0, label="# living children")
    num_abortion = forms.IntegerField(required=False, min_value=0, label="# abortions")
    num_stillbirth = forms.IntegerField(required=False, min_value=0, label="# stillbirths")
    num_large_babies = forms.IntegerField(required=False, min_value=0, label="# large babies (>8lbs)")

    has_diabetes = forms.BooleanField(required=False, label="Diabetes")
    gravida = forms.IntegerField(required=False, min_value=0, label="Gravida")
    para = forms.IntegerField(required=False, min_value=0, label="Para")

    # Optional multi-selects (IDs from reference tables if you have them)
    checklist_item_ids = forms.CharField(
        required=False,
        help_text="Comma-separated checklist item IDs (optional)"
    )
    risk_category_ids = forms.CharField(
        required=False,
        help_text="Comma-separated risk category IDs (optional)"
    )

    # NOTE: Midwife fields intentionally omitted here; passed as None on create.


class SearchActiveScheduleFilter(forms.Form):
    search = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'search',
            'class' : 'form-control', 
            'placeholder' : 'Search',
    }),
        label= 'Search',
        required= False,
    )

class StatusActiveScheduleFilter(forms.Form):
    status = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={
            'id' : 'status',
            'class' : 'form-select',
        }),
        label= 'Status',
        # required= False,
    )
    
    def __init__(self, *args, **kwargs):
        from src.infra.database.connection_adapter import ConnectionAdapter
        from src.infra.repositories.account_status_repository import AccountStatusRepository
        super().__init__(*args, **kwargs)
        status = AccountStatusRepository(ConnectionAdapter())
        self.fields['status'].choices = [('', 'All')] + [(str(row[0]), row[1]) for row in status.get_all()]

class WeekRangeActiveScheduleFilter(forms.Form):
    week_range = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={
            'id' : 'week_range',
            'class' : 'form-select',
        }),
        label= "Week Range",
        # required= False,
    )
    
    def __init__(self, *args, **kwargs):
        from src.infra.database.connection_adapter import ConnectionAdapter
        from src.infra.repositories.week_range_repository import WeekRangeRepository
        super().__init__(*args, **kwargs)
        week_range = WeekRangeRepository(ConnectionAdapter())
        self.fields['week_range'].choices = [('', 'All')] + [(str(row[0]), row[1]) for row in week_range.get_all()]

class Reschedule(forms.Form):
    week_range = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={
            'id' : 'select-week_range',
            # 'class' : 'form-select',
        }),
        label= 'Week Range',
        required= True,
    )

    reason = forms.ChoiceField(
        choices=[
            ('No one at home', 'No one at home'),
            ('Household requested new date', 'Household requested new date'),
            ('Emergency in household', 'Emergency in household'),
            ('Bad weather conditions', 'Bad weather conditions'),
            ('Health worker unavailable', 'Health worker unavailable'),
            ('Barangay activity conflict', 'Barangay activity conflict'),
            ('Incorrect address given', 'Incorrect address given'),
            ('Ongoing household event (e.g., wake, celebration)', 'Ongoing household event (e.g., wake, celebration)'),
            ('Security/safety concern', 'Security/safety concern'),
            ('Access to area restricted', 'Access to area restricted'),
            ],
        widget=forms.Select(attrs={
            'id' : 'reschedule',
            'class' : 'form-select',
        }),
        label= 'Reason',
        # required= False,
    )


class HouseholdFilters(forms.Form):
    search = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'search',
            'class' : 'form-control', 
            'placeholder' : 'Search',
        }),
        label= 'Search',
        required= False,
    )
    house_type = forms.ChoiceField(
        choices= HOUSE_TYPE_CHOICES,
        widget=forms.Select(attrs={
            'id' : 'house_type',
            'class' : 'form-select',
        }),
        label= 'House Type',
        required= False,
    )
    house_ownership = forms.ChoiceField(
        choices= HOUSE_OWNERSHIP_CHOICES,
        widget=forms.Select(attrs={
            'id' : 'house_ownership',
            'class' : 'form-select',
        }),
        label= 'House Ownership',
        required= False,
    )

class ResidentFilters(forms.Form):
    search = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'search',
            'class' : 'form-control', 
            'placeholder' : 'Search',
        }),
        label= 'Search',
        required= False,
    )
    purok_sitio = forms.ChoiceField(
        choices= PUROK_SITIO_CHOICES,
        widget=forms.Select(attrs={
            'id' : 'purok_sitio',
            'class' : 'form-select',
        }),
        label= 'Purok / Sitio',
        required= False,
    )

class HouseholdHistoryFilters(forms.Form):
    search = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'search',
            'class' : 'form-control', 
            'placeholder' : 'Search household head or address',
        }),
        label= 'Search',
        required= False,
    )
    quarter = forms.ChoiceField(
        choices=[
            ('1', 'Q1 (Jan-Mar)'),
            ('2', 'Q2 (Apr-Jun)'),
            ('3', 'Q3 (Jul-Sep)'),
            ('4', 'Q4 (Oct-Dec)'),
        ],
        widget=forms.Select(attrs={
            'id' : 'quarter',
            'class' : 'form-select',
        }),
        label= 'Quarter',
        required= True,
    )
    year = forms.IntegerField(
        widget=forms.NumberInput(attrs={
            'id' : 'year',
            'class' : 'form-control',
            'placeholder' : 'Year (e.g., 2024)',
            'min': '2000',
            'max': '2100',
        }),
        label= 'Year',
        required= True,
    )
    house_type = forms.ChoiceField(
        choices= HOUSE_TYPE_CHOICES,
        widget=forms.Select(attrs={
            'id' : 'house_type',
            'class' : 'form-select',
        }),
        label= 'House Type',
        required= False,
    )
    house_ownership = forms.ChoiceField(
        choices= HOUSE_OWNERSHIP_CHOICES,
        widget=forms.Select(attrs={
            'id' : 'house_ownership',
            'class' : 'form-select',
        }),
        label= 'House Ownership',
        required= False,
    )

class FamilyFilters(forms.Form):
    search = forms.CharField(
        widget=forms.TextInput(attrs={
            'id': 'search',
            'class': 'form-control',
            'placeholder': 'Search family head or family number'
        }),
        label='Search',
        required=False,
    )
    household_type = forms.ChoiceField(
        choices=HOUSEHOLD_TYPE_CHOICES,
        widget=forms.Select(attrs={
            'id': 'household_type',
            'class': 'form-select',
        }),
        label='Household Type',
        required=False,
    )
    nhts_status = forms.ChoiceField(
        choices=NHTS_STATUS_CHOICES,
        widget=forms.Select(attrs={
            'id': 'nhts_status',
            'class': 'form-select',
        }),
        label='NHTS Status',
        required=False,
    )
    indigent_status = forms.ChoiceField(
        choices=INDIGENT_STATUS_CHOICES,
        widget=forms.Select(attrs={
            'id': 'indigent_status',
            'class': 'form-select',
        }),
        label='Indigent Status',
        required=False,
    )

class FamilyHistoryFilters(forms.Form):
    search = forms.CharField(
        widget=forms.TextInput(attrs={
            'id': 'search',
            'class': 'form-control',
            'placeholder': 'Search family head, family number, or UFC number'
        }),
        label='Search',
        required=False,
    )
    quarter = forms.ChoiceField(
        choices=[
            ('1', 'Q1 (Jan-Mar)'),
            ('2', 'Q2 (Apr-Jun)'),
            ('3', 'Q3 (Jul-Sep)'),
            ('4', 'Q4 (Oct-Dec)'),
        ],
        widget=forms.Select(attrs={
            'id': 'quarter',
            'class': 'form-select',
        }),
        label='Quarter',
        required=True,
    )
    year = forms.IntegerField(
        widget=forms.NumberInput(attrs={
            'id': 'year',
            'class': 'form-control',
            'placeholder': 'Year (e.g., 2024)',
            'min': '2000',
            'max': '2100',
        }),
        label='Year',
        required=True,
    )
    household_type = forms.ChoiceField(
        choices=HOUSEHOLD_TYPE_CHOICES,
        widget=forms.Select(attrs={
            'id': 'household_type',
            'class': 'form-select',
        }),
        label='Household Type',
        required=False,
    )
    nhts_status = forms.ChoiceField(
        choices=NHTS_STATUS_CHOICES,
        widget=forms.Select(attrs={
            'id': 'nhts_status',
            'class': 'form-select',
        }),
        label='NHTS Status',
        required=False,
    )
    indigent_status = forms.ChoiceField(
        choices=INDIGENT_STATUS_CHOICES,
        widget=forms.Select(attrs={
            'id': 'indigent_status',
            'class': 'form-select',
        }),
        label='Indigent Status',
        required=False,
    )

# Resident Profiling Forms
class ResidentPersonalInfoForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.data.get('mobile_num') and not self.initial.get('mobile_num'):
            self.initial['mobile_num'] = '+63'
    first_name = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class': 'form-control'}))
    middle_name = forms.CharField(max_length=100, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    last_name = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class': 'form-control'}))
    suffix = forms.ChoiceField(choices=[('', 'None'), ('JR', 'Jr.'), ('SR', 'Sr.'), ('III', 'III'), ('IV', 'IV'), ('V', 'V')], required=False, widget=forms.Select(attrs={'class': 'form-select'}))
    sex = forms.ChoiceField(choices=[(1, 'Male'), (2, 'Female')], widget=forms.RadioSelect())
    dob = forms.DateField(widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}))
    civil_status = forms.ChoiceField(choices=[(1, 'Single'), (2, 'Married'), (3, 'Widowed'), (4, 'Separated'), (5, 'Divorced')], widget=forms.Select(attrs={'class': 'form-select'}))
    nationality = forms.ChoiceField(choices=[(7, 'Filipino'), (1, 'American'), (2, 'Australian'), (3, 'Brazilian'), (4, 'British'), (5, 'Canadian'), (6, 'Chinese'), (8, 'French'), (9, 'German'), (10, 'Indian'), (11, 'Indonesian'), (12, 'Italian'), (13, 'Japanese'), (14, 'Korean'), (15, 'Malaysian'), (16, 'Russian'), (17, 'Saudi'), (18, 'Spanish'), (19, 'Thai'), (20, 'Vietnamese')], widget=forms.Select(attrs={'class': 'form-select'}))
    religion = forms.ChoiceField(choices=[(12, 'Roman Catholic'), (8, 'Islam'), (2, 'Born Again'), (7, 'Iglesia Ni Cristo'), (1, 'Agnostic'), (3, 'Buddhist'), (4, 'Christian'), (5, 'Evangelical'), (6, 'Hindu'), (9, "Jehovah's Witness"), (10, 'Orthodox'), (11, 'Protestant'), (13, 'Seventh-Day Adventist'), (14, 'Others')], widget=forms.Select(attrs={'class': 'form-select'}))
    mobile_num = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+63'}))
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={'class': 'form-control'}))

class ResidentSocioeconomicForm(forms.Form):
    educational_attainment = forms.ChoiceField(choices=[(1, 'No Formal Education'), (2, 'Kinder'), (3, 'Elementary Student'), (4, 'Elementary Undergrad'), (5, 'Elementary Graduate'), (6, 'High School Student'), (7, 'High School Undergrad'), (8, 'High School Graduate'), (9, 'Vocational Course'), (10, 'College Student'), (11, 'College Undergrad'), (12, 'College Graduate'), (13, 'Postgraduate')], required=False, widget=forms.Select(attrs={'class': 'form-select'}))
    employment_status = forms.ChoiceField(choices=[(1, 'Employed'), (2, 'Unemployed'), (3, 'OFW'), (5, 'Retired'), (6, 'Self-Employed'), (7, 'Pensioner'), (8, 'Housewife'), (9, 'Freelancer'), (10, 'Disabled'), (11, 'Looking for Work'), (12, 'Part-Time'), (13, 'Full-Time'), (14, 'Underemployed')], widget=forms.Select(attrs={'class': 'form-select'}))
    occupation = forms.CharField(max_length=100, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    monthly_income = forms.ChoiceField(choices=[(1, 'Below ₱5,000'), (2, '₱5,001 - ₱10,000'), (3, '₱10,001 - ₱15,000'), (4, '₱15,001 - ₱20,000'), (5, '₱20,001 - ₱30,000'), (6, '₱30,001 - ₱50,000'), (7, '₱50,001 - ₱75,000'), (8, '₱75,001 - ₱100,000'), (9, 'Above ₱100,000')], widget=forms.Select(attrs={'class': 'form-select'}))
    residency_month = forms.ChoiceField(choices=[(str(i), datetime(2000, i, 1).strftime('%B')) for i in range(1, 13)], widget=forms.Select(attrs={'class': 'form-select'}))
    residency_year = forms.ChoiceField(choices=[(str(y), str(y)) for y in range(datetime.now().year, datetime.now().year - 100, -1)], widget=forms.Select(attrs={'class': 'form-select'}))

