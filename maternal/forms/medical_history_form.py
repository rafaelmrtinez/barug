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

    def __init__(self, maternal_repository: MaternalHealthRecordRepository, mhr_id: int | None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)