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

    ALLOWED_ROLES = { "bhw", "Barangay Health Worker", "barangay health worker", "BHW", "BARANGAY HEALTH WORKER" }

    def __init__(self, role, maternal_repository: MaternalHealthRecordRepository, maternal_id: int | None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
        self._maternal_repository = maternal_repository
        self.field_by_role_policy(role, maternal_id)
    
    def field_by_role_policy(self, role, maternal_id: int | None):
        if role in self.ALLOWED_ROLES:
            """ Make certain fields readonly for BHW role
            - Family Number
            - Date of Birth
            - Age
            - Age group
            - Address
            - Occupation
            - BMI and BMI category
            """
            readonly_fields = [
                'family_no',
                'date_of_birth',
                'age',
                'age_group',
                'address',
                'occupation',
                'bmi',
                'bmi_category',
            ]
            for field_name in readonly_fields:
                field = self.fields.get(field_name)
                if field:
                    field.disabled = True
        else:
            for field in self.fields.values():
                field.disabled = True
                
            if maternal_id is not None:
                
                data = self._maternal_repository.fetch_all_mhr_form_basic_info_by_mhr_id(maternal_id)
                if data:
                    self.fields['family_no'].initial = data.get('family_number')
                    self.fields['name'].initial = data.get('full_name')
                    self.fields['date_of_birth'].initial = data.get('date_of_birth')
                    self.fields['age'].initial = data.get('age')
                    self.fields['address'].initial = data.get('address')
                    self.fields['husband_name'].initial = data.get('husband_full_name') or 'N/A'
                    self.fields['occupation'].initial = data.get('occupation') or 'N/A'