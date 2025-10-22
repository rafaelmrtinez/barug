from django import forms
from maternal.forms.maternal_identification_form import add_bootstrap_classes
from decimal import Decimal
from datetime import date

class ChildVisitForm(forms.Form):
    date = forms.DateField(
        label="Date", 
        required=True,
        widget=forms.DateInput(attrs={'type': 'date'}),
        error_messages={'required': 'Please provide the date of visit.'},
    )
    age = forms.DecimalField(
        label="Age (years)", required=True, min_value=Decimal('0.1'), max_value=Decimal('5'),
        error_messages={
            'required': 'Please provide the age.',
            'min_value': 'Age must be positive.',
            'max_value': 'Age must be less than 5 years for child center visits.'
        }
    )
    weight = forms.DecimalField(
        label="Weight (kg)", required=True, min_value=Decimal('0.1'), max_digits=5, decimal_places=2,
        error_messages={'required': 'Please provide the weight.', 'min_value': 'Weight must be positive.'}
    )
    temp = forms.DecimalField(
        label="Temp. (°C)", required=True, min_value=Decimal('0.1'), max_value=Decimal('45.0'), max_digits=4, decimal_places=1,
        error_messages={'required': 'Please provide the temperature.', 'min_value': 'Temperature too low.', 'max_value': 'Temperature too high.'}
    )
    height = forms.DecimalField(
        label="Height (cm)", required=True, min_value=Decimal('0.1'), max_digits=5, decimal_places=2,
        error_messages={'required': 'Please provide the height.', 'min_value': 'Height must be positive.'}
    )
    findings = forms.CharField(
        label="Findings", required=True, max_length=500,
        error_messages={'required': 'Please provide the findings.'}
    )
    notes = forms.CharField(label="Notes", required=False, max_length=1000)
    form_type = forms.CharField(widget=forms.HiddenInput(attrs={'id': 'id_form_type_cv'}), initial='child_visit_form')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)

    def clean_date(self):
        visit_date = self.cleaned_data.get('date')
        if visit_date and visit_date > date.today():
            raise forms.ValidationError("Visit date cannot be in the future.")
        return visit_date

    def clean_findings(self):
        findings = self.cleaned_data.get('findings', '').strip()
        if not findings:
            raise forms.ValidationError("Findings cannot be empty.")
        return findings

    def clean_notes(self):
        notes = self.cleaned_data.get('notes', '').strip()
        return notes

    def clean(self):
        cleaned_data = super().clean()
        age = cleaned_data.get('age')
        weight = cleaned_data.get('weight')
        height = cleaned_data.get('height')

        # Ensure age < 5 (child center restriction)
        if age and age > Decimal('5'):
            self.add_error('age', 'Child center visits are only for children under 5 years old.')

        # Optional cross-field validation (BMI check)
        if age and weight and height:
            bmi = weight / (height / 100) ** 2
            if bmi < 10:
                self.add_error('weight', 'Weight seems unusually low for the given height.')

        return cleaned_data
