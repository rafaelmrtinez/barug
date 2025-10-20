from django import forms

from maternal.forms.maternal_identification_form import add_bootstrap_classes
from maternal.repository import MaternalHealthRecordRepository


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