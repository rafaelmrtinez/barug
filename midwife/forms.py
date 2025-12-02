from django import forms

BMI_CHOICES = (
    (1, "Low"),
    (2, "Normal"),
    (3, "High"),
)

ROLE_CHOICES = [
    (3,  "Barangay Captain"), (4,  "Barangay Secretary"),(5,  "Barangay Treasurer"), 
    (6,  "Barangay Clerk"), (7,  "Barangay Lupon President"), (8,  "Barangay Lupon Member"), 
    (9,  "Barangay Health Worker"), (10, "Nurse"), (11, "Midwife"),
]

PUROK_CHOICES = [
    (1, "Kanipaan"), (2, "Pampango"), (3, "Lutaw-Lutaw"), (4, "Mauco"),
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
        # required= False,
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
        choices=[],
        widget=forms.Select(attrs={
            'id' : 'reschedule',
            'class' : 'form-select',
        }),
        label= 'Reason',
        # required= False,
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
    assigned_purok = forms.ChoiceField(
        choices=[(""  , "— Select Assigned Purok —")] + PUROK_CHOICES,
        widget=forms.Select(attrs={
            'id': 'assigned_purok',
            'class': 'form-select',
            'name': 'assigned_purok',
        }),
        label='Assigned Purok',
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
    role = forms.ChoiceField(
        choices = [],
        widget=forms.Select(attrs={
            'id' : 'role',
            'class' : 'form-select',
    }),
        label= 'Select a Role',
        required= True,
    )
    # hidden twin so the value is submitted even when the select is disabled
    role_locked = forms.CharField(widget=forms.HiddenInput(), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].choices = ROLE_CHOICES
        self.fields["role"].initial = "9"          # ← the value you want
        self.fields["role"].disabled = True        # ← disable the dropdown
        self.fields["role"].widget.attrs["disabled"] = "disabled"  # (adds HTML attr)
        self.fields["role_locked"].initial = self.fields["role"].initial

    def clean(self):
        cd = super().clean()
        # ensure cleaned_data['role'] is set even if the field is disabled
        if self.fields["role"].disabled:
            cd["role"] = self.fields["role"].initial or cd.get("role_locked")
        return cd
    
    purok_sitio = forms.TypedChoiceField(
        label="Assign to Purok/Sitio",
        choices=[("", "— Select Purok/Sitio —")] + PUROK_CHOICES,
        coerce=int, empty_value=None, required=False,
        widget=forms.Select(attrs={"id": "purok_sitio", "class": "form-select"})
    )


class StaffUpdateForm(forms.Form):
    assigned_purok = forms.ChoiceField(
        choices=[(""  , "— Select Purok/Sitio —")] + PUROK_CHOICES,
        widget=forms.Select(attrs={
            'class': 'form-select',
        }),
        label='Assigned Purok',
        required=False,
    )

class ResidentProfileform(forms.Form):
    res_code = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'res_code',
            'class' : 'form-control',
            'placeholder' : 'Resident ID',
    }),
        label= 'Resident ID',
        # required= False,
    )
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'username',
            'class' : 'form-control',
            'placeholder' : 'Username',
    }),
        label= 'Username',
        # required= False,
    )
    temp_pass = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'temp_pass'
    }),
        label= 'Temporary Password',
        # required= False,
    )
    res_status = forms.ChoiceField(
        widget=forms.Select(attrs={
            'id' : 'res_status',
            'class' : 'form-select',
    }),
        label= 'Resident Status',
        # required= False,
    )
    reg_method = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'reg_method',
            'class' : 'form-control',
            'placeholder' : 'Registration Method',
    }),
        label= 'Registration Method',
        # required= False,
    )
    reg_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type' : 'date',
            'id' : 'reg_date',
            'class' : 'form-control',
            'placeholder' : 'Registration Date',
    }),
        label= 'Registration Date',
        # required= False,
    )
    acc_status = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'acc_status',
            'class' : 'form_control',
            'placeholder' : 'Account Status',
    }),
        label= 'Account Status',
        # required= False,
    )
    added_by = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'added_by',
            'class' : 'form-control',
            'placeholder' : 'Addedd By'
    }),
        label= 'Added By',
        # required= False,
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
        required= False
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
    province = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'province',
            'class' : 'form-control',
            'placeholder' : 'Province',
    }),
        label= 'Province',
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
    }),
        label= 'Front of the ID',
        required= True, 
    )
    back_id = forms.ImageField(
        widget=forms.ClearableFileInput(attrs={
            'id' : 'back_id',
            'class' : 'form-control',
    }),
        label= 'Back of the ID',
        required= True, 
    )
    res_img = forms.ImageField(
        widget=forms.ClearableFileInput(attrs={
            'id' : 'res_img',
            'class' : 'form-control',
    }),
        label= 'Selfie Holding the Valid ID',
        required= True,
    )
    proof = forms.ImageField(
        widget=forms.ClearableFileInput(attrs={
            'id' : 'proof',
            'class' : 'form-control',
    }),
        label= 'Proof of Employment',
        required= True,
    )