from django import forms

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
        required= True,
    )
    suffix = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'suffix',
            'class' : 'form-control',
            'placeholder' : 'Suffix',
    }),
        label= 'Suffix',
        required= True,
    )
    sex = forms.ChoiceField(
        choices= [('male', 'Male'), ('female', 'Female')],
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
    civil_status = forms.ChoiceField(
        choices= [], 
        widget=forms.Select(attrs={
            'id' : 'civil_status',
            'class' : 'form-select',
    }),
        label= 'Civil Status',
        required= True,
    )
    nationality = forms.ChoiceField(
        choices= [], 
        widget=forms.Select(attrs={
            'id' : 'nationality',
            'class' : 'form-select',
    }),
        label= 'Nationality',
        required= True,
    )
    religion = forms.ChoiceField(
        choices= [], 
        widget=forms.Select(attrs={
            'id' : 'religion',
            'class' : 'form-select',
    }),
        label= 'Religion',
        required= True,
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
        required= True
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
            'readonly' : 'readonly',
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
    # SOCIOECONOMIC INFORMATION
    educational_attainment = forms.ChoiceField(
        choices= [], 
        widget=forms.Select(attrs={
            'id' : 'educational_attainment',
            'class' : 'form-select',
    }),
        label= 'Educatoinal Attainment',
        required= True,
    )
    employment_status = forms.ChoiceField(
        choices= [], 
        widget=forms.Select(attrs={
            'id' : 'employment_status',
            'class' : 'form-select',
    }),
        label= 'Employment Status',
        required= True,
    )
    occupation = forms.ChoiceField(
        choices= [], 
        widget=forms.Select(attrs={
            'id' : 'occupation',
            'class' : 'form-select',
    }),
        label= 'Occupation',
        required= True,
    )
    monthly_personal_income = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'monthtly_personal_income',
            'class' : 'form-control',
            'placeholder' : 'Monthly Personal Income',
    }),
        label= 'Monthly Personal Income',
        required= True,
    )
    gov_program = forms.ChoiceField(
        choices= [], 
        widget=forms.Select(attrs={
            'id' : 'gov_program',
            'class' : 'form-select',
    }),
        label= 'Goverment Program',
        required= True,
    )
    # SUPPORTING DOCUMENTS
    res_img = forms.ImageField(
        widget=forms.ClearableFileInput(attrs={
            'id' : 'res_img',
            'class' : 'form-control',
    }),
        label= 'Resident Image',
        required= False, #correct if wrong
    )
    type_of_doc = forms.ChoiceField(
        choices= [], 
        widget=forms.Select(attrs={
            'id' : 'type_of_doc',
            'class' : 'form-select',
    }),
        label= 'Type of Document',
        required= False, #correct if wrong
    )
    proof_img = forms.ImageField(
        widget=forms.ClearableFileInput(attrs={
            'id' : 'proof_img',
            'class' : 'form-control',
    }),
        label= 'Proof of Residency',
        required= False, #correct if wrong
    )

class HouseholdProfileForm(forms.Form):
    household_num = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'hh_num',
            'class' : 'form-control',
            'placeholder' : 'Household Number',
    }),
        label= 'Household Number',
        required= True,
    )
    home_address = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'home_address',
            'class' : 'form-control',
            'placeholder' : 'Home Address',
            'data-bs-toggle' : 'modal',
            'data-bs-target' : '#address_modal',
    }),
        label= 'Home Address',
        required= True
    )
    house_num = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'house_num',
            'class' : 'form-control',
            'placeholder' : 'House Number',
    }),
        label= 'House Number',
        required= True,
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
    }),
        label= 'Barangay',
        required= True,
    )
    city = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'city',
            'class' : 'form-control',
            'placeholder' : 'City',
    }),
        label= 'City',
        required= True,
    )
    household_head = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'hh_head',
            'class' : 'form-control',
            'placeholder' : 'Household Head',
    }),
        label= 'Household Head',
        required= True,
    )
    house_type = forms.ChoiceField(
        choices= [],
        widget=forms.Select(attrs={
            'id' : 'house_type',
            'class' : 'form-select',
    }),
        label= 'House Type',
        required= True,
    )
    house_ownership = forms.ChoiceField(
        choices= [],
        widget=forms.Select(attrs={
            'id' : 'house_ownership',
            'class' : 'form-select',
    }),
        label= 'House Ownership',
        required= True,
    )
    date_created = forms.DateField(
        widget=forms.DateInput(attrs={
            'type' : 'date',
            'id' : 'date_created',
            'class' : 'form-control',
            'placeholder' : 'Date Created',
    }),
        label= 'Date Created',
        # required= True,
    )
    added_by = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'added_by',
            'class' : 'form-control',
            'placeholder' : 'Added By',
    }),
        label= 'Added By',
        # required= True,
    )

class FamilyProfileForm(forms.Form):
    family_num = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'family_num',
            'class' : 'form-control',
            'placeholder' : 'Family Number',
    }),
        label= 'Family Number',
        required= True,
    )
    nhts_status = forms.ChoiceField(
        choices= [],
        widget=forms.RadioSelect(attrs={
            'id' : 'nhts_status',
            'class' : 'form-check-input',
    }),
        label= 'NHST Status',
        required= True,
    )
    indigent_status = forms.ChoiceField(
        choices= [],
        widget=forms.RadioSelect(attrs={
            'id' : 'indigent_status',
            'class' : 'form-check-input',
    }),
        label= 'Indigent Status',
        required= True,
    )
    income_source = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'income_source',
            'class' : 'form-control',
            'placeholder' : 'Source of Income',
    }),
        label= 'Source of Income',
        required= True,
    )
    monthly_income = forms.CharField(
        widget=forms.Textarea(attrs={
            'id' : 'monthly_income',
            'class' : 'form-control',
            'placeholder' : 'Family Monthly Income'
    }),
        label= 'Family Monthly Income',
        required= True,
    )
    date_created = forms.DateField(
        widget=forms.DateInput(attrs={
            'type' : 'date',
            'id' : 'date_created',
            'class' : 'form-control',
            'placeholder' : 'Date Created',
    }),
        label= 'Date Created',
        # required= True,
    )
    added_by = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'added_by',
            'class' : 'form-control',
            'placeholder' : 'Added By',
    }),
        label= 'Added By',
        # required= True,
    )