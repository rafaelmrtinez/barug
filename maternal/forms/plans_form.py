from django import forms

from maternal.forms.maternal_identification_form import add_bootstrap_classes
from maternal.repository import MaternalHealthRecordRepository


class PlanForm(forms.Form):
    # Plans
    plan_place_of_delivery = forms.CharField(required=False)
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
        