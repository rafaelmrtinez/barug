from django import forms

from maternal.forms.maternal_identification_form import add_bootstrap_classes
from maternal.repository import MaternalHealthRecordRepository


class MicroNutrientsForm(forms.Form):
    iron_folic_start = forms.DateField(required=False, widget=forms.DateInput(
        attrs={'type': 'date'}), label="Iron w/ Folic Acid (start)")
    iron_folic_end = forms.DateField(required=False, widget=forms.DateInput(
        attrs={'type': 'date'}), label="Iron w/ Folic Acid (completed)")
    deworming_date = forms.DateField(required=False, widget=forms.DateInput(
        attrs={'type': 'date'}), label="Deworming tab (preferably 3rd trimester) date given")
    form_type = forms.CharField(initial="micro_nutrients_form", widget=forms.HiddenInput(
        attrs={'id': 'micro_nutrients_form'}
    ))

    def __init__(self, mhr_repo: MaternalHealthRecordRepository, mhr_id: int,  *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
        self._mhr_repo = mhr_repo
        self._micronutrients_data = self._mhr_repo.fetch_micronutrients_by_mhr_id(mhr_id)
        
        print(f"DEBUG: Fetched micronutrients data for MHR ID {mhr_id}: {self._micronutrients_data}")

        # populate form fields only if values are present (not None)
        if self._micronutrients_data:
            iron_start = self._micronutrients_data.get("iron_start_date")
            iron_end = self._micronutrients_data.get("iron_end_date")
            deworm = self._micronutrients_data.get("deworming_date")

            if iron_start is not None:
                self.fields["iron_folic_start"].initial = iron_start
                self.initial["iron_folic_start"] = iron_start
            if iron_end is not None:
                self.fields["iron_folic_end"].initial = iron_end
                self.initial["iron_folic_end"] = iron_end
            if deworm is not None:
                self.fields["deworming_date"].initial = deworm
                self.initial["deworming_date"] = deworm

    def clean(self):
        cleaned_data = super().clean()
        if not any(cleaned_data.values()):
            raise forms.ValidationError(
                "At least one micronutrient field must be filled."
            )
        return cleaned_data