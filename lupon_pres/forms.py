# lupon_pres/forms.py
from django import forms
from django.core.exceptions import ValidationError

class SearchPerson(forms.Form):
    """Form for searching persons"""
    query = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by name...'
        })
    )

class ResidentProfileform(forms.Form):
    """Form for resident profile information"""
    first_name = forms.CharField(max_length=100, required=True)
    last_name = forms.CharField(max_length=100, required=True)
    middle_name = forms.CharField(max_length=100, required=False)
    suffix = forms.CharField(max_length=20, required=False)
    
    # Add other fields as needed
    email = forms.EmailField(required=False)
    mob_num = forms.CharField(max_length=20, required=False)
    
    # Choice fields - these would be populated from database
    sex = forms.ChoiceField(choices=[], required=True)
    civil_status = forms.ChoiceField(choices=[], required=True)
    nationality = forms.ChoiceField(choices=[], required=True)
    religion = forms.ChoiceField(choices=[], required=True)
    type_of_id = forms.ChoiceField(choices=[], required=False)
    
    # Date fields
    dob = forms.DateField(required=True, widget=forms.DateInput(attrs={'type': 'date'}))
    
    # Address fields
    street = forms.CharField(max_length=255, required=False)
    purok_sitio = forms.CharField(max_length=100, required=False)
    barangay = forms.CharField(max_length=100, required=False)
    city = forms.CharField(max_length=100, required=False)
    
    # File fields
    front_id = forms.FileField(required=False)
    back_id = forms.FileField(required=False)
    res_img = forms.FileField(required=False)
    proof = forms.FileField(required=False)

class Schedule(forms.Form):
    """Form for scheduling"""
    day = forms.ChoiceField(
        choices=[
            (1, 'Monday'),
            (2, 'Tuesday'), 
            (3, 'Wednesday'),
            (4, 'Thursday'),
            (5, 'Friday'),
            (6, 'Saturday'),
            (7, 'Sunday'),
        ],
        required=True
    )
    time_start = forms.TimeField(
        widget=forms.TimeInput(attrs={'type': 'time'}),
        required=True
    )
    time_end = forms.TimeField(
        widget=forms.TimeInput(attrs={'type': 'time'}),
        required=True
    )

class StaffFilters(forms.Form):
    """Form for filtering staff"""
    role_id = forms.ChoiceField(choices=[], required=False)
    day_id = forms.ChoiceField(choices=[], required=False)
    account_status_id = forms.ChoiceField(choices=[], required=False)

class UpdateInfo(forms.Form):
    """Form for updating information"""
    role = forms.ChoiceField(
        choices=[
            (8, 'Barangay Lupon Member'),
        ],
        required=True
    )
    
    # Schedule fields for dynamic addition
    schedules = forms.CharField(widget=forms.HiddenInput(), required=False)