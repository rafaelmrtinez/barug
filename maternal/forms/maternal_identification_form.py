import decimal
from django import forms

from maternal.constants import AGE_GROUPS
from maternal.repository import MaternalHealthRecordRepository
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
            self.fields['family_no'].widget.attrs['readonly'] = True
            self.fields['date_of_birth'].widget.attrs['readonly'] = True
            self.fields['age'].widget.attrs['readonly'] = True
            self.fields['age_group'].widget.attrs['readonly'] = True
            self.fields['address'].widget.attrs['readonly'] = True
            self.fields['husband_name'].widget.attrs['readonly'] = True
            self.fields['occupation'].widget.attrs['readonly'] = True
            self.fields['bmi_category'].widget.attrs['readonly'] = True
            self.fields['bmi'].widget.attrs['readonly'] = True
        else:
            # disable all
            for field in self.fields.values():
                field.disabled = True
                
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
