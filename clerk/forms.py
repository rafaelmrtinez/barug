from django import forms
from decimal import Decimal
from datetime import date, timedelta
import re

CIVIL_STATUS_CHOICES = [
    ("", "— Select Civil Status —"),
    (1, "SINGLE"),
    (2, "MARRIED"),
    (3, "WIDOWED"),
    (4, "SEPARATED"),
    (5, "DIVORCED"),
]

NATIONALITY_CHOICES = [
    ("", "— Select Nationality —"),
    (1, "AMERICAN"),
    (2, "AUSTRALIAN"),
    (3, "BRAZILIAN"),
    (4, "BRITISH"),
    (5, "CANADIAN"),
    (6, "CHINESE"),
    (7, "FILIPINO"),
    (8, "FRENCH"),
    (9, "GERMAN"),
    (10, "INDIAN"),
    (11, "INDONESIAN"),
    (12, "ITALIAN"),
    (13, "JAPANESE"),
    (14, "KOREAN"),
    (15, "MALAYSIAN"),
    (16, "RUSSIAN"),
    (17, "SAUDI"),
    (18, "SPANISH"),
    (19, "THAI"),
    (20, "VIETNAMESE"),
    (21, "OTHERS"),
]

RELIGION_CHOICES = [
    ("", "— Select Religion —"),
    (1, "AGNOSTIC"),
    (2, "BORN AGAIN"),
    (3, "BUDDHIST"),
    (4, "CHRISTIAN"),
    (5, "EVANGELICAL"),
    (6, "HINDU"),
    (7, "IGLESIA NI CRISTO"),
    (8, "ISLAM"),
    (9, "JEHOVAH'S WITNESS"),
    (10, "ORTHODOX"),
    (11, "PROTESTANT"),
    (12, "ROMAN CATHOLIC"),
    (13, "SEVENTH-DAY ADVENTIST"),
    (14, "OTHERS"),
]

VALID_ID_TYPE_CHOICES = [
    ("", "— Select ID Type —"),
    (1,  "PHILIPPINE PASSPORT"),
    (2,  "PHILIPPINE NATIONAL ID"),
    (3,  "SSS/UMID CARD"),
    (4,  "GSIS ECARD"),
    (5,  "PRC ID"),
    (6,  "DRIVER'S LICENSE"),
    (7,  "PHILHEALTH ID"),
    (8,  "VOTER'S ID"),
    (9,  "POSTAL ID"),
    (10, "SENIOR CITIZEN ID"),
    (11, "PWD ID"),
    (12, "OWWA ID"),
    (13, "IBP ID"),
    (14, "TIN ID"),
    (15, "SCHOOL ID"),
    (16, "EPHIL ID"),
]

BUSINESS_CATEGORY_CHOICES = [
    ("", "— Select category —"),
    (40, "Bakeries, Pastry Shop"),
    (39, "Cellphones and Gadget Stores"),
    (27, "Commercial Stalls for Rent"),
    (38, "Computer Shops"),
    (45, "Dry Goods"),
    (36, "Educational Institutions (Private)"),
    (25, "Financial Institutions (Lending Companies)"),
    (31, "Firearms Stores"),
    (43, "Fitness Gyms"),
    (32, "Furniture Shops, Appliance Store"),
    (28, "Gasoline Stations"),
    (42, "General Merchandise"),
    (4,  "Groceries Store"),
    (34, "Hotels, Apartments"),
    (29, "Motorcycle and other Vehicle Dealers"),
    (33, "Motorcycle/Bicycle Supplies Stores"),
    (49, "Night Market"),
    (35, "Restaurants, Canteens"),
    (47, "Sari-Sari Store"),
    (48, "Special Permit"),
    (30, "Specialization Clinics such as Dental Clinics, ENT, Pedia Clinics"),
    (46, "Tailoring Services"),
    (37, "Vehicle Services, Auto Repair Shop"),
    (26, "Videoke Bars"),
    (44, "Water Refilling Stations"),
]

OWNERSHIP_TYPE_CHOICES = [
    ("", "— All ownerships —"),
    (1, "SOLE PROPRIETORSHIP"),
    (2, "PARTNERSHIP"),
    (3, "CORPORATION"),
    (4, "COOPERATIVE"),
    (5, "ONE PERSON CORPORATION"),
    (6, "OTHERS"),
]

BUSINESS_STATUS_CHOICES = [
    ("", "— All statuses —"),
    (1, "ACTIVE"),
    # (2, "INACTIVE"),
    # (3, "SUSPENDED"),
    # (4, "REVOKED"),
    (5, "CLOSED"),
    (6, "EXPIRED"),
    (7, "PENDING"),
]

OPERATING_DAY_CHOICES = [
    ("", "— Select Day —"),
    (1, "Monday"),
    (2, "Tuesday"),
    (3, "Wednesday"),
    (4, "Thursday"),
    (5, "Friday"),
    (6, "Saturday"),
    (7, "Sunday"),
]

class RequestedDocsFilters(forms.Form):
    search = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'search',
            'class' : 'form-control', 
            'placeholder' : 'Search',
        }),
        label= 'Search',
        required= False,
    )
    doc_status = forms.ChoiceField(
        choices= [],
        widget=forms.Select(attrs={
            'id' : 'b_type',
            'class' : 'form-select',
        }),
        label= 'Status',
        required= False,
    )
    doc_type = forms.ChoiceField(
        choices= [],
        widget=forms.Select(attrs={
            'id' : 'b_type',
            'class' : 'form-select',
        }),
        label= 'Document Type',
        required= False,
    )

class SearchVerificationRequest(forms.Form):
    search = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'search',
            'class' : 'form-control', 
            'placeholder' : 'Search',
    }),
        label= 'Search',
        # required= False,
    )

class BusinessFilters(forms.Form):
    search = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'search',
            'class' : 'form-control', 
            'placeholder' : 'Search',
        }),
        label= 'Search',
        required= False,
    )
    b_category = forms.ChoiceField(
        choices= BUSINESS_CATEGORY_CHOICES,
        widget=forms.Select(attrs={
            'id' : 'b_category',
            'class' : 'form-select',
        }),
        label= 'Business Type',
        required= False,
    )
    ownership_type = forms.ChoiceField(
        choices= OWNERSHIP_TYPE_CHOICES,
        widget=forms.Select(attrs={
            'id' : 'ownership_type',
            'class' : 'form-select',
        }),
        label= 'Ownership Type',
        required= False,
    )
    status = forms.ChoiceField(
        choices= BUSINESS_STATUS_CHOICES,
        widget=forms.Select(attrs={
            'id' : 'status',
            'class' : 'form-select',
        }),
        label= 'Status',
        required= False,
    )

class RenewalFilters(forms.Form):
    search = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'search',
            'class' : 'form-control', 
            'placeholder' : 'Search',
        }),
        label= 'Search',
        required= False,
    )
    clearance_state = forms.ChoiceField(
        choices= BUSINESS_CATEGORY_CHOICES,
        widget=forms.Select(attrs={
            'id' : 'clearance_state',
            'class' : 'form-select',
        }),
        label= 'Clearance State',
        required= False,
    )

class SearchBusinessOwner(forms.Form):
    search = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'search',
            'class' : 'form-control', 
            'placeholder' : 'Search',
            "autocomplete": "off",
    }),
        label= 'Search by Resident ID or Full Name',
        required= True,
    )

class SelectOwnerForm(forms.Form):
    owner_person_id = forms.IntegerField(widget=forms.HiddenInput())
    search = forms.CharField(required=False, widget=forms.HiddenInput)

def _norm_email(txt: str | None) -> str | None:
    if not txt:
        return None
    return txt.strip().lower() or None

MOBILE_RE = re.compile(r"\D+")
def _norm_mobile(txt: str | None) -> str | None:
    """
    Keep digits only; PH-friendly:
    - strip +63 or leading 0
    - return last 11 (or last 10) digits if present
    """
    if not txt:
        return None
    digits = MOBILE_RE.sub("", txt)
    if digits.startswith("63"):
        digits = digits[2:]
    if digits.startswith("0"):
        digits = digits[1:]
    if len(digits) >= 11:
        return digits[-11:]
    if len(digits) >= 10:
        return digits[-10:]
    return digits or None
 
class BusinessOwnerInfo(forms.Form):
    # PERSONAL INFORMATION
    last_name = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'last_name',
            'class' : 'form-control',
            'placeholder' : 'Last Name',
            'style': 'text-transform: uppercase;',
            "autocomplete": "family-name",
    }),
        label= 'Last Name',
        required= True,
        error_messages={"required": "Last name is required."},
    )
    first_name = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'first_name',
            'class' : 'form-control',
            'placeholder' : 'First Name',
            'style': 'text-transform: uppercase;',
            "autocomplete": "given-name",
    }),
        label= 'First Name',
        required= True,
        error_messages={"required": "First name is required."},
    )
    middle_name = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'middle_name',
            'class' : 'form-control',
            'placeholder' : 'Middle Name',
            'style': 'text-transform: uppercase;',
            "autocomplete": "additional-name",
    }),
        label= 'Middle Name',
        required= False,
        error_messages={"required": "Middle name is required."},
    )
    suffix = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'suffix',
            'class' : 'form-control',
            'placeholder' : 'Suffix',
            'style': 'text-transform: uppercase;',
            "autocomplete": "suffix",
    }),
        label= 'Suffix',
        required= False,
        error_messages={"required": "Suffix is required."},
    )
    sex = forms.ChoiceField(
        choices= [(1, 'Male'), (2, 'Female')],
        widget=forms.RadioSelect(attrs={
            'id' : 'sex',
            'class' : 'form-check-input',
    }),
        label= 'Sex',
        required= True,
        error_messages={"required": "Please select sex."},
    )
    dob = forms.DateField(
        widget=forms.DateInput(attrs={
            'type' : 'date',
            'id' : 'dob',
            'class' : 'form-control',
            'placeholder' : 'Date of Birth',
    }),
        label= 'Date of Birth',
        required= True,
        error_messages={"required": "Date of birth is required."},
    )
    civil_status = forms.ChoiceField(
        choices= CIVIL_STATUS_CHOICES, 
        widget=forms.Select(attrs={
            'id' : 'civil_status',
            'class' : 'form-select',
    }),
        label= 'Civil Status',
        required= True,
    )
    nationality = forms.ChoiceField(
        choices= NATIONALITY_CHOICES, 
        widget=forms.Select(attrs={
            'id' : 'nationality',
            'class' : 'form-select',
    }),
        label= 'Nationality',
        required= True,
    )
    religion = forms.ChoiceField(
        choices= RELIGION_CHOICES, 
        widget=forms.Select(attrs={
            'id' : 'religion',
            'class' : 'form-select',
    }),
        label= 'Religion',
        required= True,
    )
    # home_address = forms.CharField(
    #     widget=forms.TextInput(attrs={
    #         'id' : 'home_address',
    #         'class' : 'form-control',
    #         'placeholder' : 'Home Address',
    #         'readonly' : 'readonly',
    #         'data-bs-toggle' : 'modal',
    #         'data-bs-target' : '#address_modal',
    # }),
    #     label= 'Home Address',
    #     required= True
    # )
    street = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'street',
            'class' : 'form-control',
            'placeholder' : 'Street',
            'style': 'text-transform: uppercase;',
    }),
        label= 'Street',
        required= True,
    )
    purok_sitio = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'purok_sitio',
            'class' : 'form-control',
            'placeholder' : 'Purok / Sitio',
            'style': 'text-transform: uppercase;',
    }),
        label= 'Purok / Sitio',
        required= True,
    )
    barangay = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'barangay',
            'class' : 'form-control',
            'placeholder' : 'Barangay',
            'style': 'text-transform: uppercase;',
    }),
        label= 'Barangay',
        required= True,
    )
    city = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'city',
            'class' : 'form-control',
            'placeholder' : 'City',
            'style': 'text-transform: uppercase;',
    }),
        label= 'City',
        required= True,
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'id' : 'email',
            'class' : 'form-control',
            'placeholder' : 'Email Address',
            "autocomplete": "email",
    }),
        label= 'Email Address',
        required= True,
    )
    mob_num = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'mob_num',
            'class' : 'form-control',
            'placeholder' : 'Mobile Number',
            "inputmode": "tel",
            "autocomplete": "tel-national",
    }),
        label= 'Mobile Number',
        required= True,
    )
    # SUPPORTING DOCUMENTS
    # type_of_id = forms.ChoiceField(
    #     choices= VALID_ID_TYPE_CHOICES, 
    #     widget=forms.Select(attrs={
    #         'id' : 'type_of_id',
    #         'class' : 'form-select',
    # }),
    #     label= 'valid ID Type',
    #     required= True,
    # )
    # front_id = forms.ImageField(
    #     widget=forms.ClearableFileInput(attrs={
    #         'id' : 'front_id',
    #         'class' : 'form-control',
    # }),
    #     label= 'Front of the ID',
    #     required= True, 
    # )
    # back_id = forms.ImageField(
    #     widget=forms.ClearableFileInput(attrs={
    #         'id' : 'back_id',
    #         'class' : 'form-control',
    # }),
    #     label= 'Back of the ID',
    #     required= True, 
    # )
    def clean_email(self):
        return _norm_email(self.cleaned_data.get("email"))
    
    def clean_mob_num(self):
        return _norm_mobile(self.cleaned_data.get("mob_num"))
    
    def clean(self):
        cleaned = super().clean()

        # DOB sanity: not future, not >120 years old
        dob = cleaned.get("dob")
        if dob:
            today = date.today()
            if dob > today:
                self.add_error("dob", "Birthdate cannot be in the future.")
            else:
                oldest = today - timedelta(days=120 * 365)
                if dob < oldest:
                    self.add_error("dob", "Birthdate seems invalid (older than 120 years).")

        # If neither email nor mobile provided, nudge clerk to enter at least one contact
        # if not cleaned.get("email") and not cleaned.get("mob_num"):
        #     self.add_error("mob_num", "Provide at least one contact: mobile or email.")
        #     # (Alternatively: add to non_field_errors)

        return cleaned

class MultiFileInput(forms.ClearableFileInput):
    # 🔑 This is what enables <input multiple>
    allow_multiple_selected = True

class MultiFileField(forms.FileField):
    widget = MultiFileInput

    def clean(self, data, initial=None):
        """
        Return a list of cleaned UploadedFile objects.
        """
        if not data and self.required:
            raise forms.ValidationError(self.error_messages['required'], code='required')

        # Normalize to a list
        files = data if isinstance(data, (list, tuple)) else ([data] if data else [])
        cleaned = []
        for f in files:
            if f:  # skip Nones
                cleaned.append(super().clean(f, initial))
        if self.required and not cleaned:
            raise forms.ValidationError(self.error_messages['required'], code='required')
        return cleaned

class BusinessDetails(forms.Form):
    b_name = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'bname',
            'class' : 'form-control',
            'placeholder' : 'Business Name',
            'style': 'text-transform: uppercase;',
        }),
        label= 'Business Name',
        required= True,
    )
    b_nature = forms.CharField( 
        widget=forms.TextInput(attrs={
            'id' : 'b_nature',
            'class' : 'form-control',
            'placeholder' : 'Nature of Business (e.g., Sari-Sari Store, Eatery, etc.)',
            'style': 'text-transform: uppercase;',
    }),
        label= 'Nature of Business',
        required= True,
    )
    ownership_type = forms.ChoiceField(
        choices= OWNERSHIP_TYPE_CHOICES, 
        widget=forms.Select(attrs={
            'id' : 'ownership_type',
            'class' : 'form-select',
    }),
        label= 'Ownership Type',
        required= True,
    )
    b_category = forms.ChoiceField(
        choices= BUSINESS_CATEGORY_CHOICES, 
        widget=forms.Select(attrs={
            'id' : 'b_category',
            'class' : 'form-select',
    }),
        label= 'Business Category',
        required= True,
    )
    b_address = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'b_address',
            'class' : 'form-control',
            'placeholder' : 'Business Address',
            'readonly' : 'readonly',
            'data-bs-toggle' : 'modal',
            'data-bs-target' : '#address_modal',
            'style': 'text-transform: uppercase;',
    }),
        label= 'Business Address',
        required= True
    )
    street = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'street',
            'class' : 'form-control',
            'placeholder' : 'Street',
            'style': 'text-transform: uppercase;',
    }),
        label= 'Street',
        required= True,
    )
    purok_sitio = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'purok_sitio',
            'class' : 'form-control',
            'placeholder' : 'Purok / Sitio',
            'style': 'text-transform: uppercase;',
    }),
        label= 'Purok / Sitio',
        required= True,
    )
    barangay = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'barangay',
            'class' : 'form-control',
            'placeholder' : 'Barangay',
            'readonly' : 'readonly',
            'style': 'text-transform: uppercase;',
    }),
        label= 'Barangay',
        required= True,
    )
    city = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'city',
            'class' : 'form-control',
            'placeholder' : 'City',
            'readonly' : 'readonly',
            'style': 'text-transform: uppercase;',
    }),
        label= 'City',
        required= True,
    )
    # Hidden fields filled by the map script
    latitude = forms.DecimalField(
        required=True,
        max_digits=10,
        decimal_places=7,
        widget=forms.HiddenInput(attrs={'id': 'latitude'}),
    )
    longitude = forms.DecimalField(
        required=True,
        max_digits=10,
        decimal_places=7,
        widget=forms.HiddenInput(attrs={'id': 'longitude'}),
    )
    # Hidden fields filled by the map script
    latitude = forms.DecimalField(
        required=False,
        max_digits=10,
        decimal_places=7,
        widget=forms.HiddenInput(attrs={'id': 'latitude'}),
    )
    longitude = forms.DecimalField(
        required=False,
        max_digits=10,
        decimal_places=7,
        widget=forms.HiddenInput(attrs={'id': 'longitude'}),
    )
    b_desc = forms.CharField(
        widget=forms.Textarea(attrs={
            'id' : 'b_desc',
            'class' : 'form-control',
            'placeholder' : 'e.g., near the barangay hall / corner of …',
            'rows' : 3,
            'style': 'text-transform: uppercase;',
    }),
        label= 'Location Description',
        required= True,
    )
    date_est = forms.DateField(
        widget=forms.DateInput(attrs={
            'type' : 'date',
            'id' : 'date_est',
            'class' : 'form-control',
            'placeholder' : 'Date Established',
    }),
        label= 'Date Established',
        required= True,
    )
    dti = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'dti',
            'class' : 'form-control',
            'placeholder' : 'DTI/SEC Registration Number',
            'autocomplete' : 'off',
    }),
        label= 'DTI/SEC Registration Number',
        required= False,
    )
    capital_invested = forms.DecimalField(
        widget=forms.NumberInput(attrs={
            'id' : 'capital_invested',
            'class' : 'form-control',
            'placeholder' : 'Capital Invested',
            'inputmode' : 'decimal',
        }),
        label= 'Capital Invested',
        required= True,
        min_value=Decimal('0.00'),
        decimal_places=2,
        max_digits=14,
    )
    prevgross = forms.DecimalField(
        widget=forms.NumberInput(attrs={
            'id' : 'prevgross',
            'class' : 'form-control',
            'placeholder' : 'Total Gross Sales of Previous Year',
            'inputmode' : 'decimal',
        }),
        label= 'Total Gross Sales of Previous Year',
        required= True,
        min_value=Decimal('0.00'),
        decimal_places=2,
        max_digits=14,
    )
    inc_est = forms.DecimalField(
        widget=forms.NumberInput(attrs={
            'id' : 'inc_est',
            'class' : 'form-control',
            'placeholder' : 'Monthly Gross Income Estimate',
            'inputmode' : 'decimal',
        }),
        label= 'Monthly Gross Income Estimate',
        required= True,
        min_value=Decimal('0.00'),
        decimal_places=2,
        max_digits=14,
    )
    emp_num = forms.IntegerField(
        widget=forms.NumberInput(attrs={
            'id' : 'emp_num',
            'class' : 'form-control',
            'placeholder' : 'No. of Employees (including owner)',
            'inputmode' : 'numeric',
        }),
        label= 'No. of Employees (including owner)',
        required= True,
        min_value=0,
    )
    opt_days_start = forms.ChoiceField(
        choices= OPERATING_DAY_CHOICES, 
        widget=forms.Select(attrs={
            'id' : 'opt_days_start',
            'class' : 'form-select',
    }),
        label= 'Operating Days',
        required= True,
    )
    opt_days_end = forms.ChoiceField(
        choices= OPERATING_DAY_CHOICES, 
        widget=forms.Select(attrs={
            'id' : 'opt_days_end',
            'class' : 'form-select',
    }),
        label= 'Operating Days',
        required= True,
    )
    opt_start = forms.TimeField(
        widget=forms.TimeInput(attrs={
            'id' : 'opt_start',
            'class' : 'form-control',
            'placeholder' : 'Operating Hours - Start',
            'type' : 'time',
        }),
        label= 'Operating Hours - Start',
        required= True,
    )
    opt_end = forms.TimeField(
        widget=forms.TimeInput(attrs={
            'id' : 'opt_end',
            'class' : 'form-control',
            'placeholder' : 'Operating Hours - End',
            'type' : 'time',
        }),
        label= 'Operating Hours - End',
        required= True,
    )
    # prev_clearance = forms.ChoiceField(
    #     choices= [('yes', 'Yes'), ('no', 'No')],
    #     widget=forms.RadioSelect(attrs={
    #         'id' : 'prev_clearance',
    #         'class' : 'form-check-input',
    # }),
    #     label= 'Has previous Barangay Clearance?',
    #     required= True,
    # )
    proof = MultiFileField(
        label='Proof of Business (lease, photos, permit, etc.)',
        required=True,
        widget=MultiFileInput(attrs={
            'id': 'proof',
            'class': 'form-control',
            'accept': 'image/*,application/pdf',
            'multiple': True,
        }),
    )

    def clean(self):
        cleaned = super().clean()

        # Ownership-based DTI rule
        ot_val = cleaned.get('ownership_type')  # ChoiceField returns the key (often str)
        dti = (cleaned.get('dti') or '').strip()

        # Map id -> label so we can check by label (safe if IDs change)
        id_to_label = {str(k): v for (k, v) in self.fields['ownership_type'].choices}
        label = (id_to_label.get(str(ot_val)) or "").upper()

        # ✅ Only SOLE PROPRIETORSHIP must provide DTI
        needs_dti = "SOLE PROPRIETORSHIP" in label

        if needs_dti and not dti:
            self.add_error('dti', "DTI/SEC registration number is required for Sole Proprietorship.")

        # Time sanity check
        t_start = cleaned.get('opt_start')
        t_end = cleaned.get('opt_end')
        if t_start and t_end and t_end <= t_start:
            self.add_error('opt_end', "End time must be later than start time.")

        return cleaned
