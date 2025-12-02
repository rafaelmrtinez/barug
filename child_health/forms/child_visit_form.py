from django import forms
from maternal.forms.maternal_identification_form import add_bootstrap_classes
from decimal import Decimal
from datetime import date
from maternal.forms.form_utils import FormUtils
from src.infra.utilities.custom_date_time_util import DateAndTimeUtility

class ChildVisitForm(forms.Form):
    date = forms.DateField(
        label="Date", 
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
        error_messages={'required': 'Please provide the date of visit.'},
    )
    age = forms.DecimalField(
        label="Age (month/s or year/s)", required=False, min_value=Decimal('0.1'), max_value=Decimal('5'),
        error_messages={
            'required': 'Please provide the age.',
            'min_value': 'Age must be positive.',
            'max_value': 'Age must be less than 5 years for child center visits.'
        }
    )
    weight = forms.DecimalField(
        label="Weight (kg)", required=False, min_value=Decimal('0.1'), max_digits=5, decimal_places=2,
        error_messages={'required': 'Please provide the weight.', 'min_value': 'Weight must be positive.'}
    )
    temp = forms.DecimalField(
        label="Temp. (°C)", required=False, min_value=Decimal('0.1'), max_value=Decimal('45.0'), max_digits=4, decimal_places=1,
        error_messages={'required': 'Please provide the temperature.', 'min_value': 'Temperature too low.', 'max_value': 'Temperature too high.'}
    )
    height = forms.DecimalField(
        label="Height (cm)", required=False, min_value=Decimal('0.1'), max_digits=5, decimal_places=2,
        error_messages={'required': 'Please provide the height.', 'min_value': 'Height must be positive.'}
    )
    findings = forms.CharField(
        label="Findings", required=False, max_length=1000,
        widget=forms.Textarea(attrs={
            'rows': 4,
        }),
        error_messages={'required': 'Please provide the findings.'}
    )
    notes = forms.CharField(
        label="Notes",
        required=False,
        max_length=1000,
        error_messages={'required': 'Please provide the notes.'},
        widget=forms.Textarea(attrs={
            'rows': 4,
        }),
    )
    form_type = forms.CharField(widget=forms.HiddenInput(attrs={'id': 'id_form_type_cv'}), initial='child_visit_form')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)

    def clean(self):
        cleaned_data = super().clean()
        # 1) Automate the date to today's PH date (override whatever was posted)
        try:
            today = DateAndTimeUtility.parse_date(DateAndTimeUtility.get_current_date()) or date.today()
        except Exception:
            today = date.today()
        cleaned_data['date'] = today

        # 2) Age must be less than 5 years (strictly)
        age = cleaned_data.get('age')
        if age is None:
            self.add_error('age', 'Please provide the age.')
            return cleaned_data
        try:
            if isinstance(age, Decimal):
                age_val = age
            else:
                age_val = Decimal(str(age))
        except Exception:
            self.add_error('age', 'Enter a valid age in years (numbers only).')
            return cleaned_data

        if age_val >= Decimal('5'):
            self.add_error('age', 'Age must be less than 5 years for child center visits.')
            return cleaned_data

        # 3) Numeric fields: weight, temp, height — ensure presence and reasonable values
        weight = cleaned_data.get('weight')
        temp = cleaned_data.get('temp')
        height = cleaned_data.get('height')

        if weight in (None, ''):
            self.add_error('weight', 'Please provide the weight.')
            return cleaned_data
        if temp in (None, ''):
            self.add_error('temp', 'Please provide the temperature.')
            return cleaned_data
        if height in (None, ''):
            self.add_error('height', 'Please provide the height.')
            return cleaned_data

        # Basic sanity bounds already present on fields — still defensively check ranges
        try:
            w = Decimal(str(weight))
            if w <= Decimal('0'):
                self.add_error('weight', 'Weight must be a positive number.')
                return cleaned_data
        except Exception:
            self.add_error('weight', 'Enter a valid weight (numbers only).')
            return cleaned_data

        try:
            t = Decimal(str(temp))
            if t <= Decimal('0') or t > Decimal('45'):
                self.add_error('temp', 'Enter a realistic temperature in °C (e.g., 36.5).')
                return cleaned_data
        except Exception:
            self.add_error('temp', 'Enter a valid temperature (numbers only).')
            return cleaned_data

        try:
            h = Decimal(str(height))
            if h <= Decimal('0'):
                self.add_error('height', 'Height must be a positive number.')
                return cleaned_data
        except Exception:
            self.add_error('height', 'Enter a valid height (numbers only).')
            return cleaned_data

        # 4/5/6) Findings required, notes optional — sanitize and reject emojis/unusual entries
        findings = cleaned_data.get('findings')
        if findings in (None, ''):
            self.add_error('findings', 'Please provide the findings.')
            return cleaned_data

        findings_norm, findings_err = FormUtils.sanitize_text(str(findings), 'Findings')
        if findings_err:
            self.add_error('findings', findings_err)
            return cleaned_data

        notes = cleaned_data.get('notes')
        if notes in (None, ''):
            notes_norm = None
        else:
            notes_norm, notes_err = FormUtils.sanitize_text(str(notes), 'Notes')
            if notes_err:
                self.add_error('notes', notes_err)
                return cleaned_data

        # 7) Friendly final: write normalized values back
        cleaned_data['age'] = age_val
        cleaned_data['weight'] = w
        cleaned_data['temp'] = t
        cleaned_data['height'] = h
        cleaned_data['findings'] = findings_norm
        cleaned_data['notes'] = notes_norm

        return cleaned_data
