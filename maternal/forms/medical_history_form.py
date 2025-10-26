from django import forms

from maternal.forms.maternal_identification_form import add_bootstrap_classes
from maternal.repository import MaternalHealthRecordRepository


class MedicalHistoryForm(forms.Form):
    ## Medical history
    previous_illness = forms.CharField(
        required=False, label="Previous illness")
    previous_hospitalization = forms.CharField(
        required=False, label="Previous hospitalization")
    previous_preg_complications = forms.CharField(
        required=False, label="Previous pregnancy complications")
    form_type = forms.CharField(
        widget=forms.HiddenInput(attrs={'id': 'medical_history_form'}), initial="medical_history_form"
    )

    def __init__(self, maternal_repository: MaternalHealthRecordRepository, mhr_id: int | None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
        self._maternal_repository = maternal_repository
        existing_data = self._maternal_repository.fetch_medical_history_by_mhr_id(mhr_id) if mhr_id else None
        self.__ui_default_display(existing_data)
        self.__ui_display_policy()

    def __ui_display_policy(self):
        if self.fields['previous_illness'].initial:
            self.fields['previous_illness'].widget.attrs['readonly'] = True
        if self.fields['previous_hospitalization'].initial:
            self.fields['previous_hospitalization'].widget.attrs['readonly'] = True
        if self.fields['previous_preg_complications'].initial:
            self.fields['previous_preg_complications'].widget.attrs['readonly'] = True

    def __ui_default_display(self, existing_data):
        if existing_data:
            self.fields['previous_illness'].initial = existing_data.get('previous_illness', '')
            self.fields['previous_hospitalization'].initial = existing_data.get('previous_hospitalization', '')
            self.fields['previous_preg_complications'].initial = existing_data.get('previous_preg_complication', '')