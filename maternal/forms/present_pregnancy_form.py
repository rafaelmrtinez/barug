from django import forms

from maternal.forms.maternal_identification_form import add_bootstrap_classes
from maternal.repository import MaternalHealthRecordRepository

class PresentPregnancyForm(forms.Form):
    # Present pregnancy
    gravida = forms.IntegerField(required=False)
    para = forms.IntegerField(required=False)
    fullterm = forms.IntegerField(required=False)
    preterm = forms.IntegerField(required=False)
    lmp = forms.DateField(required=False, widget=forms.DateInput(
        attrs={'type': 'date'}), label="LMP")
    edc = forms.DateField(required=False, widget=forms.DateInput(
        attrs={'type': 'date'}), label="EDC")

    def __init__(self, mhr_repo: MaternalHealthRecordRepository, mhr_id: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)