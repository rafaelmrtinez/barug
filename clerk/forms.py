from django import forms
from decimal import Decimal

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
    b_type = forms.ChoiceField(
        choices= [],
        widget=forms.Select(attrs={
            'id' : 'b_type',
            'class' : 'form-select',
        }),
        label= 'Business Type',
        required= False,
    )
    ownership_type = forms.ChoiceField(
        choices= [],
        widget=forms.Select(attrs={
            'id' : 'ownership_type',
            'class' : 'form-select',
        }),
        label= 'Ownership Type',
        required= False,
    )
    status = forms.ChoiceField(
        choices= [],
        widget=forms.Select(attrs={
            'id' : 'status',
            'class' : 'form-select',
        }),
        label= 'Status',
        required= False,
    )

class SearchBusinessOwner(forms.Form):
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

class SelectOwnerForm(forms.Form):
    owner_person_id = forms.IntegerField(widget=forms.HiddenInput())

class BusinessOwnerInfo(forms.Form):
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

class BusinessDetails(forms.Form):
    b_name = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'bname',
            'class' : 'form-control',
            'placeholder' : 'Business Name',
        }),
        label= 'Business Name',
        required= True,
    )
    b_type = forms.ChoiceField(
        choices= [], 
        widget=forms.Select(attrs={
            'id' : 'b_type',
            'class' : 'form-select',
    }),
        label= 'Business Type',
        required= True,
    )
    b_nature = forms.ChoiceField( 
        widget=forms.Select(attrs={
            'id' : 'b_nature',
            'class' : 'form-control',
            'placeholder' : 'Nature of Business',
    }),
        label= 'Nature of Business',
        required= True,
    )
    ownership_type = forms.ChoiceField(
        choices= [], 
        widget=forms.Select(attrs={
            'id' : 'ownership_type',
            'class' : 'form-select',
    }),
        label= 'Ownership Type',
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
    }),
        label= 'Business Address',
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
    b_desc = forms.CharField(
        widget=forms.Textarea(attrs={
            'id' : 'b_desc',
            'class' : 'form-control',
            'placeholder' : 'e.g., near the barangay hall / corner of …',
            'rows' : 3,
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
        required= True,
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
    opt_days = forms.MultipleChoiceField(
        choices= [], 
        widget=forms.SelectMultiple(attrs={
            'id' : 'opt_days',
            'class' : 'form-select',
            'size' : 1,
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
    prev_clearance = forms.ChoiceField(
        choices= [('yes', 'Yes'), ('no', 'No')],
        widget=forms.RadioSelect(attrs={
            'id' : 'prev_clearance',
            'class' : 'form-check-input',
    }),
        label= 'Has previous Barangay Clearance?',
        required= True,
    )
    proof = forms.FileField(
        widget=forms.ClearableFileInput(attrs={
            'id' : 'proof',
            'class' : 'form-control',
        }),
        label= 'Proof of Business (lease, photos, permit, etc.)',
        required= True, 
    )