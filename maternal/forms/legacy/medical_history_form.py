from django import forms

from maternal.forms.maternal_identification_form import add_bootstrap_classes
from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository


class MedicalHistoryForm(forms.Form):
    ## Medical history
    previous_illness = forms.CharField(
        required=False, label="Previous illness")
    previous_hospitalization = forms.CharField(
        required=False, label="Previous hospitalization")
    previous_preg_complications = forms.CharField(
        required=False, label="Previous pregnancy complications")

    def __init__(self, maternal_repository: MaternalHealthRecordRepository, mhr_id: int | None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
        # You can add bootstrap classes or other initializations here if needed
        self._maternal_repository = maternal_repository
        medical_history_data = self._maternal_repository.fetch_obstetric_history_by_mhr_id(mhr_id)
        if medical_history_data:
            self.fields['previous_illness'].initial = medical_history_data.get('previous_illness', '')
            self.fields['previous_hospitalization'].initial = medical_history_data.get('previous_hospitalization', '')
            self.fields['previous_preg_complications'].initial = medical_history_data.get('previous_preg_complications', '')