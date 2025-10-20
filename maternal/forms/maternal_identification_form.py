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
    name = forms.CharField(required=True, label="Name")
    date_of_birth = forms.DateField(required=False, widget=forms.DateInput(
        attrs={'type': 'date'}), label="Date of birth")
    age = forms.IntegerField(required=False)
    age_group = forms.ChoiceField(choices=AGE_GROUPS, required=False)
    address = forms.CharField(
        required=False, widget=forms.Textarea(attrs={'rows': 2}))
    husband_name = forms.CharField(required=False, label="Husband’s name")
    occupation = forms.CharField(required=False)
    weight_kg = forms.DecimalField(
        required=False, max_digits=5, decimal_places=2, label="Weight (kg)")
    height_cm = forms.DecimalField(
        required=False, max_digits=5, decimal_places=2, label="Height (cm)")
    bmi = forms.DecimalField(
        required=False, max_digits=5, decimal_places=2, label="BMI")
    bmi_category = forms.CharField(required=False, label="BMI category")
    person_id = forms.IntegerField(required=False, widget=forms.HiddenInput())
    husband_id = forms.IntegerField(required=False, widget=forms.HiddenInput())

    W_PLUS_R_PRIVILEGE = { "bhw", "Barangay Health Worker", "barangay health worker", "BHW", "BARANGAY HEALTH WORKER" }

    def __init__(self, path: str | None, role: str | None, maternal_repository: MaternalHealthRecordRepository, maternal_id: int | None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
        self._maternal_repository = maternal_repository
        
        if role in self.W_PLUS_R_PRIVILEGE and "health-record-form" in path:
            for field in self.fields.values():
                field.disabled = True
        
        if role not in self.W_PLUS_R_PRIVILEGE:
            # Disable all fields for non-BHW roles
            for field in self.fields.values():
                field.disabled = True