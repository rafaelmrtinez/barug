from django import forms

class ResidentProfileform(forms.Form) :
    res_id = forms.IntegerField(
        widget=forms.HiddenInput(attrs={
            'id' : 'res_id',
    }))
    res_code = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'res_code',
            'class' : 'form-control',
            'placeholder' : 'Resident ID',
    }),
        label= 'Resident ID',
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
        choices= [],
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
    address = forms.ChoiceField(
        choices= [], 
        widget=forms.Select(attrs={
            'id' : 'address',
            'class' : 'form-select',
    }),
        label= 'Home Address',
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
            'placeholder' : 'Monhly Personal Income',
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
    proof_img = forms.ImageField(
        widget=forms.ClearableFileInput(attrs={
            'id' : 'proof_img',
            'class' : 'form-control',
    }),
        label= 'Proof of Residency',
        required= False, #correct if wrong
    )