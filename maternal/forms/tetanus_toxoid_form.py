from django import forms

from maternal.forms.maternal_identification_form import add_bootstrap_classes
from maternal.repository import MaternalHealthRecordRepository


class TetanusToxoidForm(forms.Form):
    # Tetanus toxoid dates
    tt1_date = forms.DateField(required=False, widget=forms.DateInput(
        attrs={'type': 'date'}), label="TT1")
    tt2_date = forms.DateField(required=False, widget=forms.DateInput(
        attrs={'type': 'date'}), label="TT2")
    tt3_date = forms.DateField(required=False, widget=forms.DateInput(
        attrs={'type': 'date'}), label="TT3")
    tt4_date = forms.DateField(required=False, widget=forms.DateInput(
        attrs={'type': 'date'}), label="TT4")
    tt5_date = forms.DateField(required=False, widget=forms.DateInput(
        attrs={'type': 'date'}), label="TT5")
    fim_date = forms.DateField(required=False, widget=forms.DateInput(
        attrs={'type': 'date'}), label="FIM")
    
    LABEL_TO_FIELD  = {
            "TT1": "tt1_date",
            "TT2": "tt2_date",
            "TT3": "tt3_date",
            "TT4": "tt4_date",
            "TT5": "tt5_date",
        }
    
    def __init__(self, mhr_repo: MaternalHealthRecordRepository, mhr_id: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)