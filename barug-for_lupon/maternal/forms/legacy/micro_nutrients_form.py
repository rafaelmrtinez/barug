from django import forms

from maternal.forms.maternal_identification_form import add_bootstrap_classes
from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository


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
        self._mhr_id = mhr_id
        micro_nutrients_data = mhr_repo.fetch_single_micro_nutrients_by_mhr_id(int(mhr_id))
        print("MICRO NUTRIENTS DATA:", micro_nutrients_data)
        if micro_nutrients_data:
            self.fields['iron_folic_start'].initial = micro_nutrients_data.get('iron_folic_start', None)
            self.fields['iron_folic_end'].initial = micro_nutrients_data.get('iron_folic_end', None)
            self.fields['deworming_date'].initial = micro_nutrients_data.get('deworming_date', None)