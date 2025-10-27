from django import forms
from django.forms import formset_factory
from datetime import date

from maternal.constants import DELIVERY_TYPE_CHOICES, GENDER_CHOICES, OUTCOME_CHOICES
from maternal.forms.maternal_identification_form import add_bootstrap_classes
from maternal.forms.form_utils import FormUtils

class PreviousPregnancyForm(forms.Form):
    delivery_date   = forms.DateField(required=True, widget=forms.DateInput(attrs={'type': 'date'}), label="Date of delivery")
    # Prepend a default 'Select ...' choice so the form shows a placeholder option
    _OUTCOME_CHOICES = [('', 'Select Outcome')] + list(OUTCOME_CHOICES)
    _DELIVERY_TYPE_CHOICES = [('', 'Select Type of Delivery')] + list(DELIVERY_TYPE_CHOICES)
    _GENDER_CHOICES = [('', 'Select Gender')] + list(GENDER_CHOICES)

    outcome         = forms.ChoiceField(
        choices=_OUTCOME_CHOICES,
        required=True,
        error_messages={
            'required': 'Please select the pregnancy outcome.'
        }
    )
    delivery_type   = forms.ChoiceField(
        choices=_DELIVERY_TYPE_CHOICES,
        required=True,
        label="Type of delivery",
        error_messages={
            'required': 'Please select the delivery type.'
        }
    )
    baby_weight_kg  = forms.DecimalField(
        required=True,
        label="Baby's weight (kg)",
        max_digits=5,
        decimal_places=2,
        error_messages={
            'required': "Please enter the baby's weight in kilograms (e.g. 3.25).",
            'invalid': "Please enter a valid weight (numbers only, decimal allowed)."
        }
    )
    gender          = forms.ChoiceField(
        choices=_GENDER_CHOICES,
        required=True,
        error_messages={
            'required': 'Please select the baby\'s gender.'
        }
    )
    ballard_score   = forms.IntegerField(
        required=True,
        label="Ballard score",
        error_messages={
            'required': 'Please enter the Ballard score.',
            'invalid': 'Please enter a whole number for the Ballard score.'
        }
    )
    apgar_score     = forms.IntegerField(
        required=True,
        label="Apgar score",
        error_messages={
            'required': 'Please enter the Apgar score.',
            'invalid': 'Please enter a whole number for the Apgar score.'
        }
    )

    form_type = forms.CharField(initial="previous_pregnancy_form", widget=forms.HiddenInput(
        attrs={'id': 'previous_pregnancy_form'}
    ))
    
    # Accept custom kwargs so formset can pass them safely
    def __init__(self, *args, mhr_repository=None, maternal_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
        # store optional repository/context for future server-side checks
        self._mhr_repository = mhr_repository
        self._maternal_id = maternal_id

    def clean(self):
        cleaned_data = super().clean()

        # Sanitize and validate date
        delivery_date = cleaned_data.get('delivery_date')
        if delivery_date:
            if isinstance(delivery_date, date) and delivery_date > date.today():
                self.add_error('delivery_date', 'Delivery date cannot be in the future.')

        # Validate and sanitize baby_weight_kg
        baby_weight = cleaned_data.get('baby_weight_kg')
        if baby_weight is not None:
            try:
                # baby_weight is Decimal from the field; ensure positive and reasonable
                if baby_weight <= 0:
                    self.add_error('baby_weight_kg', "Baby's weight must be greater than zero.")
                elif baby_weight > 10:
                    self.add_error('baby_weight_kg', "Please confirm the baby's weight — values over 10 kg are unusual.")
            except Exception:
                # Field-level validators should catch invalid formats; keep this defensive
                self.add_error('baby_weight_kg', "Invalid baby weight value.")

        # Validate integer ranges: Ballard (0-50), Apgar (0-10)
        ballard = cleaned_data.get('ballard_score')
        if ballard is not None:
            if ballard < 0 or ballard > 50:
                self.add_error('ballard_score', 'Ballard score must be between 0 and 50.')

        apgar = cleaned_data.get('apgar_score')
        if apgar is not None:
            if apgar < 0 or apgar > 10:
                self.add_error('apgar_score', 'Apgar score must be between 0 and 10.')

        # Sanitize and check for emojis in choice/text-like fields
        for field_name in ('outcome', 'delivery_type', 'gender'):
            val = cleaned_data.get(field_name)
            if val is None:
                continue
            # remove non-printable and detect emoji in the string representation
            normalized = FormUtils.remove_non_printable(str(val).strip())

            # If the user left the default placeholder selected, reject it
            if normalized == '':
                label = self.fields[field_name].label or field_name.replace('_', ' ').capitalize()
                # Friendly, non-technical message
                self.add_error(field_name, f"Please select {label.lower()}.")
                continue

            if FormUtils.contains_emoji(normalized):
                label = self.fields[field_name].label or field_name.replace('_', ' ').capitalize()
                self.add_error(field_name, f"{label}: please remove emojis — use plain text only.")
                continue

            cleaned_data[field_name] = normalized

        # Map delivery_type and gender to IDs for downstream use (keeps previous behavior)
        delivery_type = str(cleaned_data.get('delivery_type') or '').lower()
        if delivery_type:
            if delivery_type == 'nsvd':
                cleaned_data['delivery_type_id'] = 1
            elif delivery_type == 'cs':
                cleaned_data['delivery_type_id'] = 2

        gender = str(cleaned_data.get('gender') or '').lower()
        if gender:
            if gender == 'female':
                cleaned_data['gender_id'] = 2
            elif gender == 'male':
                cleaned_data['gender_id'] = 1

        return cleaned_data


PreviousPregnancyFormSet = formset_factory(
    PreviousPregnancyForm,
    extra=0,
    can_delete=True,
)
