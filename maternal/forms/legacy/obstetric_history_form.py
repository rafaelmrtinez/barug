from django import forms

from maternal.forms.maternal_identification_form import add_bootstrap_classes
from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository


class ObstetricHistoryForm(forms.Form):
    # Obstetric history
    children_born_alive = forms.IntegerField(
        required=False, label="No. of children born alive")
    living_children = forms.IntegerField(
        required=False, label="No. of living children")
    abortions = forms.IntegerField(required=False, label="No. of abortion")
    stillbirths = forms.IntegerField(
        required=False, label="No. of still births / fetal death")
    history_large_babies = forms.IntegerField(
        required=False, label="History of large babies (≥ 3.6 kg / 8 lbs)")
    diabetes_history = forms.BooleanField(
        required=False, label="Diabetes (history)")
    
    def __init__(self, maternal_repository: MaternalHealthRecordRepository, mhr_id: int | None,  *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
        self._maternal_repository = maternal_repository
        
        obsetric_data = self._maternal_repository.fetch_obstetric_history_by_mhr_id(mhr_id)
        if obsetric_data:
            self.fields['children_born_alive'].initial = obsetric_data.get('num_children_born_alive', 0)
            self.fields['living_children'].initial = obsetric_data.get('num_children_living', 0)
            self.fields['abortions'].initial = obsetric_data.get('num_abortion', 0)
            self.fields['stillbirths'].initial = obsetric_data.get('num_stillbirth_or_fetal_death', 0)
            self.fields['history_large_babies'].initial = obsetric_data.get('num_large_babies', 0)
            self.fields['diabetes_history'].initial = obsetric_data.get('has_diabetes', False)