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
        present_pregnancy_data = mhr_repo.fetch_latest_present_pregnancy_by_mhr_id(mhr_id)
        print("PRESENT PREGNANCY DATA:", present_pregnancy_data)
        if present_pregnancy_data:
            self.fields['gravida'].initial = present_pregnancy_data.get('gravida')
            self.fields['para'].initial = present_pregnancy_data.get('para')
            self.fields['fullterm'].initial = present_pregnancy_data.get('is_fullterm')
            self.fields['preterm'].initial = present_pregnancy_data.get('is_preterm')
            self.fields['lmp'].initial = present_pregnancy_data.get('lmp')
            self.fields['edc'].initial = present_pregnancy_data.get('edc')