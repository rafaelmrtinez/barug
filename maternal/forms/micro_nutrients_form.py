from django import forms

from maternal.forms.maternal_identification_form import add_bootstrap_classes
from maternal.repository import MaternalHealthRecordRepository


class MicroNutrientsForm(forms.Form):
    # Micronutrients
    iron_folic_start = forms.DateField(required=False, widget=forms.DateInput(
        attrs={'type': 'date'}), label="Iron w/ Folic Acid (start)")
    iron_folic_end = forms.DateField(required=False, widget=forms.DateInput(
        attrs={'type': 'date'}), label="Iron w/ Folic Acid (completed)")
    deworming_date = forms.DateField(required=False, widget=forms.DateInput(
        attrs={'type': 'date'}), label="Deworming tab (preferably 3rd trimester) date given")

    def __init__(self, mhr_repo: MaternalHealthRecordRepository, mhr_id: int,  *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
        self._mhr_repo = mhr_repo