import decimal
from django import forms

from maternal.constants import AGE_GROUPS
from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository
from src.infra.database.connection_adapter import ConnectionAdapter

def add_bootstrap_classes(self):
    for fname, field in self.fields.items():
        # Text, number, date, select, textarea
        if isinstance(field.widget, (forms.TextInput, forms.NumberInput, forms.DateInput, forms.Select, forms.Textarea)):
            field.widget.attrs.setdefault('class', 'form-control')
        # Checkbox
        elif isinstance(field.widget, forms.CheckboxInput):
            field.widget.attrs.setdefault('class', 'form-check-input')
        # CheckboxSelectMultiple
        elif isinstance(field.widget, forms.CheckboxSelectMultiple):
            field.widget.attrs.setdefault('class', 'form-check-input')

class MaternalIdentificationForm(forms.Form):
    # Identification
    family_no = forms.CharField(required=False, label="Family No.")
    name = forms.CharField(required=False, label="Name")
    date_of_birth = forms.DateField(required=False, widget=forms.DateInput(
        attrs={'type': 'date'}), label="Date of birth")
    age = forms.DecimalField(required=False)
    age_group = forms.CharField(required=False, label="Age group")
    address = forms.CharField(
        required=False, widget=forms.Textarea(attrs={'rows': 2}))
    husband_name = forms.CharField(required=False, label="Husband’s name")
    occupation = forms.CharField(required=False)
    weight_kg = forms.DecimalField(
        required=True, max_digits=5, decimal_places=2, label="Weight (kg)", error_messages={'required': 'Please enter weight in kilograms.'})
    height_cm = forms.DecimalField(
        required=True, max_digits=5, decimal_places=2, label="Height (cm)")
    bmi = forms.DecimalField(
        required=True, max_digits=5, decimal_places=2, label="BMI", error_messages={'required': 'Please enter BMI.'})
    bmi_category = forms.CharField(required=True, label="BMI category", error_messages={'required': 'Please enter BMI category.'})
    person_id = forms.IntegerField(required=True, widget=forms.HiddenInput(), error_messages={'required': 'Please select a motger.'})
    husband_id = forms.IntegerField(required=False, widget=forms.HiddenInput())
    is_transferred = forms.BooleanField(required=False, label="Transferred")

    def __init__(self, role: str | None, maternal_repository: MaternalHealthRecordRepository, maternal_id: int | None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
        self._maternal_repository = maternal_repository
        self._maternal_id = maternal_id
        
        if role == "barangay health worker":
            self.__health_worker_policy()
        elif role == "midwife":
            self.__midwife_policy()
        else:
            # handle not allowed roles
            self.__disable_all()

    def __midwife_policy(self):
        self.__disable_all()
        basic_info = self._maternal_repository.fetch_all_mhr_form_basic_info_by_mhr_id(self._maternal_id)
        if basic_info:
            self.__midwife_ui_autofilled(basic_info)
        else:
            self.__display_not_applicable()

    def __midwife_ui_autofilled(self, basic_info):
        self.fields['family_no'].initial = basic_info.get('family_number', '') or 'N/A'
        self.fields['name'].initial = basic_info.get('mother_full_name', '') or 'N/A'
        self.fields['date_of_birth'].initial = basic_info.get('mother_birthdate', '') or 'N/A'
        mothers_age: float = None
        try:
            mothers_age = float(basic_info.get('mother_age', ''))
            
            if mothers_age:
                # convert to integer to nearest ones
                mothers_age = int(round(mothers_age))

        except (TypeError, ValueError):
            mothers_age = None
        
        if mothers_age:
            self.fields['age'].initial = mothers_age
        else:
            self.fields['age'].initial = 'N/A'            
        
        self.__ui_age_group_assignment(basic_info.get('mother_age', ''))
        self.fields['address'].initial = basic_info.get('mother_address', '') or 'N/A'
        self.fields['husband_name'].initial = basic_info.get('husband_full_name', '') or 'N/A'
        self.fields['occupation'].initial = basic_info.get('mother_occupation', '') or 'N/A'
        self.fields['weight_kg'].initial = basic_info.get('mother_weight', '') or ''
        self.fields['height_cm'].initial = basic_info.get('mother_height', '') or ''
        self.fields['bmi_category'].initial = basic_info.get('bmi_status', '') or 'N/A'
        self.fields['bmi'].initial = basic_info.get('mother_bmi', '') or 'N/A'

    def __ui_age_group_assignment(self, age):
        if age:
            if age >= 10 and age <= 14:
                self.fields['age_group'].initial = "10 – 14"
            elif age >= 15 and age <= 19:
                self.fields['age_group'].initial = "15 – 19"
            elif age > 19:
                self.fields['age_group'].initial = "20 and above"
            else:
                self.fields['age_group'].initial = 'N/A'
        

    def __display_not_applicable(self):
        self.fields['family_no'].initial = 'N/A'
        self.fields['date_of_birth'].initial = 'N/A'
        self.fields['age'].initial = 'N/A'
        self.fields['age_group'].initial = 'N/A'
        self.fields['address'].initial = 'N/A'
        self.fields['husband_name'].initial = 'N/A'
        self.fields['occupation'].initial = 'N/A'
        self.fields['bmi_category'].initial = 'N/A'
        self.fields['bmi'].initial = 'N/A'

    def __disable_all(self):
        for field in self.fields.values():
            field.disabled = True

    def __health_worker_policy(self):
        self.fields['family_no'].widget.attrs['readonly'] = True
        self.fields['date_of_birth'].widget.attrs['readonly'] = True
        self.fields['age'].widget.attrs['readonly'] = True
        self.fields['age_group'].widget.attrs['readonly'] = True
        self.fields['address'].widget.attrs['readonly'] = True
        self.fields['husband_name'].widget.attrs['readonly'] = True
        self.fields['occupation'].widget.attrs['readonly'] = True
        self.fields['bmi_category'].widget.attrs['readonly'] = True
        self.fields['bmi'].widget.attrs['readonly'] = True
                
    def clean(self):
        cleaned_data = super().clean()

        bmi_category = cleaned_data.get("bmi_category")
        if bmi_category:
            bmi_category = bmi_category.lower()
            if bmi_category == "low":
                cleaned_data["bmi_status_id"] = 1
            elif bmi_category == "normal":
                cleaned_data["bmi_status_id"] = 2
            else:
                cleaned_data["bmi_status_id"] = 3

        try:
            if cleaned_data.get('weight_kg') is not None:
                cleaned_data['weight_kg'] = decimal.Decimal(cleaned_data['weight_kg'])
            if cleaned_data.get('height_cm') is not None:
                cleaned_data['height_cm'] = decimal.Decimal(cleaned_data['height_cm'])
        except decimal.InvalidOperation:
            self.add_error('weight_kg', "Invalid weight value.")
            self.add_error('height_cm', "Invalid height value.")

        return cleaned_data
