from django import forms

from maternal.forms.maternal_identification_form import add_bootstrap_classes
from maternal.repository import MaternalHealthRecordRepository
from maternal.forms.form_utils import FormUtils


class PlanForm(forms.Form):
    # Plans
    plan_place_of_delivery = forms.CharField(
        required=True,
        max_length=255,
        widget=forms.TextInput(attrs={'maxlength': '255'}),
        error_messages={
            'required': "Please enter the planned place of delivery. If not applicable, enter 'N/A'.",
            'max_length': 'Place of delivery must be 255 characters or fewer.',
            'invalid': 'Please enter a valid place of delivery.'
        }
    )
    plan_newborn_screening = forms.BooleanField(
        required=False, label="Plan for newborn screening")
    form_type = forms.CharField(widget=forms.HiddenInput(attrs={'id': 'plan_form'}), initial='plan_form')
    
    def __init__(self, mhr_repo: MaternalHealthRecordRepository, mhr_id: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
        self._mhr_repo = mhr_repo
        self._mhr_id = mhr_id
        
        self._existing_data = self._mhr_repo.fetch_nbs_data_by_mhr_id(mhr_id)
        # If repository returned existing plan data, pre-populate the form
        # and make the fields read-only/disabled so the user cannot change them.
        if self._existing_data:
            # sample returned keys: {'new_born_screening_plan': True, 'place_of_delivery_plan': 'ccmc'}
            nbs_val = self._existing_data.get('new_born_screening_plan')
            pod_val = self._existing_data.get('place_of_delivery_plan')

            # Map repository keys to form field names and set initial values
            if pod_val is not None:
                self.fields['plan_place_of_delivery'].initial = pod_val
                # Make text input readonly/disabled
                self.fields['plan_place_of_delivery'].disabled = True
                self.fields['plan_place_of_delivery'].widget.attrs.update({'readonly': 'readonly'})

            if nbs_val is not None:
                # BooleanField expects a boolean initial
                self.fields['plan_newborn_screening'].initial = bool(nbs_val)
                # Disable the checkbox to prevent changes
                self.fields['plan_newborn_screening'].disabled = True

    def clean(self):
        cleaned_data = super().clean()

        pod = cleaned_data.get('plan_place_of_delivery')

        # If field-level validators already flagged an error, stop to avoid duplicates
        if self.errors.get('plan_place_of_delivery'):
            return cleaned_data

        # If plan_place_of_delivery is missing, add a friendly error and return early
        if pod is None or (isinstance(pod, str) and pod.strip() == ''):
            self.add_error('plan_place_of_delivery', "Please specify the planned place of delivery. If not applicable, enter 'N/A'.")
            return cleaned_data

        # Sanitize and validate the input (no emojis, remove non-printable chars)
        normalized, err = FormUtils.sanitize_text(pod, 'Place of delivery')
        if err:
            # sanitize_text returns a friendly message when invalid (including emoji)
            self.add_error('plan_place_of_delivery', err)
            return cleaned_data

        # store normalized value back into cleaned_data
        cleaned_data['plan_place_of_delivery'] = normalized

        return cleaned_data
        