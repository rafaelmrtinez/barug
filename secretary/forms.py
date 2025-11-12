from django import forms
from django.core.exceptions import ValidationError


HOUSE_OWNERSHIP_CHOICES = [
    ("", "— All ownerships —"),
    (1, "OWNED"),
    (2, "RENTED"),
    (3, "FAMILY-OWNED"),
    (4, "GOVERNMENT HOUSING"),
    (5, "INFORMAL SETTLER"),
]

HOUSE_TYPE_CHOICES = [
    ("", "— All ownerships —"),
    (1, "CONCRETE"),
    (2, "SEMI-CONCRETE"),
    (3, "LIGHT MATERIAL"),
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
    (2, "INACTIVE"),
    (3, "SUSPENDED"),
    (4, "REVOKED"),
    (5, "CLOSED"),
    (6, "EXPIRED"),
]

ROLE_CHOICES = [
    (3,  "Barangay Captain"), (4,  "Barangay Secretary"),(5,  "Barangay Treasurer"), 
    (6,  "Barangay Clerk"), (7,  "Barangay Lupon President"), (8,  "Barangay Lupon Member"), 
    (9,  "Barangay Health Worker"), 
    # (10, "Nurse"), 
    (11, "Midwife"),
]

PUROK_CHOICES = [
    (1, "Kanipaan"), (2, "Pampango"), (3, "Lutaw-Lutaw"), (4, "Mauco"),
]

DAY_CHOICES = [
    (1, "Monday"), (2, "Tuesday"), (3, "Wednesday"), (4, "Thursday"),
    (5, "Friday"), (6, "Saturday"), (7, "Sunday"),
]

CIVIL_STATUS_CHOICES = [
    (1, "Single"), (2, "Married"), (3, "Widowed"),
    (4, "Separated"), (5, "Divorced"),
]

NATIONALITY_CHOICES = [
    (1, "American"), (2, "Australian"), (3, "Brazilian"), (4, "British"),
    (5, "Canadian"), (6, "Chinese"), (7, "Filipino"), (8, "French"),
    (9, "German"), (10, "Indian"), (11, "Indonesian"), (12, "Italian"),
    (13, "Japanese"), (14, "Korean"), (15, "Malaysian"), (16, "Russian"),
    (17, "Saudi"), (18, "Spanish"), (19, "Thai"), (20, "Vietnamese"),
    (21, "Others"),
]

RELIGION_CHOICES = [
    (1, "Agnostic"), (2, "Born Again"), (3, "Buddhist"), (4, "Christian"),
    (5, "Evangelical"), (6, "Hindu"), (7, "Iglesia ni Cristo"), (8, "Islam"),
    (9, "Jehovah's Witness"), (10, "Orthodox"), (11, "Protestant"),
    (12, "Roman Catholic"), (13, "Seventh-day Adventist"), (14, "Others"),
]

VALID_ID_TYPE_CHOICES = [
    # (1,  "Philippine Passport"),
    (2,  "Philippine National ID"), 
    # (3,  "SSS/UMID Card"), 
    # (4,  "GSIS eCard"), (5,  "PRC ID"), 
    # (6,  "Driver's License"), 
    # (7,  "PhilHealth ID"), (8,  "Voter's ID"),
    # (9,  "Postal ID"), 
    # (10, "Senior Citizen ID"), (11, "PWD ID"), (12, "OWWA ID"), (13, "IBP ID"),
    # (14, "TIN ID"), (15, "School ID"), 
    (16, "ePhil ID"),
]

STAFF_ACCOUNT_STATUS = [
    (1, "Active"), (2, "Inactive"), (3, "Deactivated"), (4, "Pending"),
]

class Schedule(forms.Form):
    day = forms.TypedChoiceField(
        label="Select a Day",
        choices=[("", "— Select a Day —")] + DAY_CHOICES,
        coerce=int, empty_value=None, required=True,
        widget=forms.Select(attrs={"id": "day", "class": "form-select"})
    )
    time_start = forms.TimeField(
        widget=forms.TimeInput(attrs={
            "id": "time_start",
            "class": "form-control",
            "type": "time",
            "step": "300",
        }),
        input_formats=["%H:%M", "%H:%M:%S"],
        label="Time-in",
        required=True,
    )
    time_end = forms.TimeField(
        widget=forms.TimeInput(attrs={
            "id": "time_end",
            "class": "form-control",
            "type": "time",
            "step": "300",
        }),
        input_formats=["%H:%M", "%H:%M:%S"],
        label="Time-out",
        required=True,
    )

class StaffFilters(forms.Form):
    search = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'search',
            'class' : 'form-control', 
            'placeholder' : 'Search Staff',
            'name': 'q'
        }),
        label='Search Staff',
        required= False,
    )
    role = forms.ChoiceField(
        choices=[("", "— Select a Role —")] + ROLE_CHOICES,
        widget=forms.Select(attrs={
            'id': 'role_filter',
            'class': 'form-select',
            'name': 'role',
        }),
        label='Filter by Role',
        required=False,
    )

    account_stat = forms.ChoiceField(
        choices=[("", "— Select Account Status —")] + STAFF_ACCOUNT_STATUS,
        widget=forms.Select(attrs={
            'id': 'account_stat',
            'class': 'form-select',
            'name': 'account_stat',
        }),
        label='Account Status',
        required=False,
    )

class SearchPerson(forms.Form):
    search = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'search',
            'class' : 'form-control', 
            'placeholder' : 'Search',
            'name': 'q'
    }),
        label= 'Search by Resident ID or Full Name',
        required= True,
    )

class ChooseRole(forms.Form):
    role = forms.TypedChoiceField(
        label="Select a Role",
        choices=[("", "— Select a Role —")] + ROLE_CHOICES,
        coerce=int, empty_value=None, required=True,
        widget=forms.Select(attrs={"id": "role", "class": "form-select"})
    )
    purok_sitio = forms.TypedChoiceField(
        label="Assign to Purok/Sitio",
        choices=[("", "— Select Purok/Sitio —")] + PUROK_CHOICES,
        coerce=int, empty_value=None, required=False,
        widget=forms.Select(attrs={"id": "purok_sitio", "class": "form-select"})
    )


class ResidentProfileform(forms.Form):
    res_code = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'res_code',
            'class' : 'form-control',
            'placeholder' : 'Resident ID',
    }),
        label= 'Resident ID',
        required= False,
    )
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'username',
            'class' : 'form-control',
            'placeholder' : 'Username',
    }),
        label= 'Username',
        required= False,
    )
    temp_pass = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'temp_pass'
    }),
        label= 'Temporary Password',
        required= False,
    )
    res_status = forms.ChoiceField(
        widget=forms.Select(attrs={
            'id' : 'res_status',
            'class' : 'form-select',
    }),
        label= 'Resident Status',
        required= False,
    )
    reg_method = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'reg_method',
            'class' : 'form-control',
            'placeholder' : 'Registration Method',
    }),
        label= 'Registration Method',
        required= False,
    )
    reg_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type' : 'date',
            'id' : 'reg_date',
            'class' : 'form-control',
            'placeholder' : 'Registration Date',
    }),
        label= 'Registration Date',
        required= False,
    )
    acc_status = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'acc_status',
            'class' : 'form_control',
            'placeholder' : 'Account Status',
    }),
        label= 'Account Status',
        required= False,
    )
    added_by = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'added_by',
            'class' : 'form-control',
            'placeholder' : 'Addedd By'
    }),
        label= 'Added By',
        required= False,
    )
    # PERSONAL INFORMATION
    last_name = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'last_name',
            'class' : 'form-control',
            'placeholder' : 'Last Name',
    }),
        label= 'Last Name',
        required= True,
    )
    first_name = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'first_name',
            'class' : 'form-control',
            'placeholder' : 'First Name',

    }),
        label= 'First Name',
        required= True,
    )
    middle_name = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'middle_name',
            'class' : 'form-control',
            'placeholder' : 'Middle Name',
    }),
        label= 'Middle Name',
        required= False,
    )
    suffix = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'suffix',
            'class' : 'form-control',
            'placeholder' : 'Suffix',
    }),
        label= 'Suffix',
        required= False,
    )
    sex = forms.ChoiceField(
        choices= [(1, 'Male'), (2, 'Female')],
        widget=forms.RadioSelect(attrs={
            'id' : 'sex',
            'class' : 'form-check-input',
    }),
        label= 'Sex',
        required= True,
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
    )

    civil_status = forms.TypedChoiceField(
        choices=[("", "— Select civil status —")] + [(str(i), n) for i, n in CIVIL_STATUS_CHOICES],
        coerce=int, empty_value=None, required=True,
        widget=forms.Select(attrs={"class": "form-select", "id": "civil_status"})
    )

    nationality = forms.TypedChoiceField(
        choices=[("", "— Select nationality —")] + [(str(i), n) for i, n in NATIONALITY_CHOICES],
        coerce=int, empty_value=None, required=True,
        widget=forms.Select(attrs={"class": "form-select", "id": "nationality"})
    )

    religion = forms.TypedChoiceField(
        choices=[("", "— Select religion —")] + [(str(i), n) for i, n in RELIGION_CHOICES],
        coerce=int, empty_value=None, required=True,
        widget=forms.Select(attrs={"class": "form-select", "id": "religion"})
    )

    home_address = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'home_address',
            'class' : 'form-control',
            'placeholder' : 'Home Address',
            'readonly' : 'readonly',
            'data-bs-toggle' : 'modal',
            'data-bs-target' : '#address_modal',
    }),
        label= 'Home Address',
        required= False,
    )
    street = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'street',
            'class' : 'form-control',
            'placeholder' : 'Street',
    }),
        label= 'Street',
        required= True,
    )
    purok_sitio = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'purok_sitio',
            'class' : 'form-control',
            'placeholder' : 'Purok / Sitio',
    }),
        label= 'Purok / Sitio',
        required= True,
    )
    barangay = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'barangay',
            'class' : 'form-control',
            'placeholder' : 'Barangay',
            # 'readonly' : 'readonly',
    }),
        label= 'Barangay',
        required= True,
    )
    city = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'city',
            'class' : 'form-control',
            'placeholder' : 'City',
            # 'readonly' : 'readonly',
    }),
        label= 'City',
        required= True,
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'id' : 'email',
            'class' : 'form-control',
            'placeholder' : 'Email Address',
    }),
        label= 'Email Address',
        required= True,
    )
    mob_num = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'mob_num',
            'class' : 'form-control',
            'placeholder' : 'Mobile Number',
    }),
        label= 'Mobile Number',
        required= True,
    )
    # # SOCIOECONOMIC INFORMATION
    # educational_attainment = forms.ChoiceField(
    #     choices= [], 
    #     widget=forms.Select(attrs={
    #         'id' : 'educational_attainment',
    #         'class' : 'form-select',
    # }),
    #     label= 'Educatoinal Attainment',
    #     required= True,
    # )
    # employment_status = forms.ChoiceField(
    #     choices= [], 
    #     widget=forms.Select(attrs={
    #         'id' : 'employment_status',
    #         'class' : 'form-select',
    # }),
    #     label= 'Employment Status',
    #     required= True,
    # )
    # occupation = forms.ChoiceField(
    #     choices= [], 
    #     widget=forms.Select(attrs={
    #         'id' : 'occupation',
    #         'class' : 'form-control',
    # }),
    #     label= 'Occupation',
    #     required= True,
    # )
    # monthly_personal_income = forms.CharField(
    #     widget=forms.TextInput(attrs={
    #         'id' : 'monthtly_personal_income',
    #         'class' : 'form-select',
    # }),
    #     label= 'Monthly Personal Income',
    #     required= True,
    # )
    # gov_program = forms.ChoiceField(
    #     choices= [], 
    #     widget=forms.Select(attrs={
    #         'id' : 'gov_program',
    #         'class' : 'form-select',
    # }),
    #     label= 'Goverment Program',
    #     required= True,
    # )
    # SUPPORTING DOCUMENTS
    type_of_id = forms.TypedChoiceField(
        label="Type of ID",
        choices=[("", "— Select ID Type —")] + [(str(i), n) for i, n in VALID_ID_TYPE_CHOICES],
        coerce=int,
        empty_value=None,
        required=True,
        widget=forms.Select(attrs={"class": "form-select", "id": "type_of_id"})
    )
    front_id = forms.ImageField(
        widget=forms.ClearableFileInput(attrs={
            'id' : 'front_id',
            'class' : 'form-control',
            'accept' : 'image/*',
    }),
        label= 'Front of the ID',
        required= True, 
    )
    back_id = forms.ImageField(
        widget=forms.ClearableFileInput(attrs={
            'id' : 'back_id',
            'class' : 'form-control',
            'accept' : 'image/*',
    }),
        label= 'Back of the ID',
        required= True, 
    )
    res_img = forms.ImageField(
        widget=forms.ClearableFileInput(attrs={
            'id' : 'res_img',
            'class' : 'form-control',
            'accept' : 'image/*',
    }),
        label= 'Selfie Holding the Valid ID',
        required= True,
    )
    proof = forms.ImageField(
        widget=forms.ClearableFileInput(attrs={
            'id' : 'proof',
            'class' : 'form-control',
            'accept' : 'image/*',
    }),
        label= 'Proof of Employment',
        required= True,
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

class AnnouncementDraftForm(forms.Form):
    title = forms.CharField(
        widget=forms.TextInput(attrs={
            "id": "title",
            "class": "form-control",
            "placeholder": "Announcement Title",
        }),
        label="Announcement Title",
        required= True,
        max_length=200,
    )

    body = forms.CharField(
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 8,
            "placeholder": "Write the announcement body here…",
        }),
        label="Body",
        required=True,
    )

    publish_at = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={
            "class": "form-control",
            "type": "datetime-local",
        }),
        label="Publish at",
        required=True,
        input_formats=["%Y-%m-%dT%H:%M"],
        help_text="Optional. Leave empty to keep as draft."
    )

    expire_at = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={
            "class": "form-control",
            "type": "datetime-local",
        }),
        label="Expire at",
        required=True,
        input_formats=["%Y-%m-%dT%H:%M"],
        help_text="Optional. If set, must be after Publish at."
    )

    def clean(self):
        cleaned = super().clean()
        publish_at = cleaned.get("publish_at")
        expire_at = cleaned.get("expire_at")

        # If both are set, ensure ordering is valid
        if publish_at and expire_at and expire_at <= publish_at:
            raise ValidationError({"expire_at": "Expire at must be after Publish at."})

        return cleaned
    
class DraftListSearch(forms.Form):
    search = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'search',
            'class' : 'form-control', 
            'placeholder' : 'Search',
        }),
        label= 'Search',
        required= False,
    )
