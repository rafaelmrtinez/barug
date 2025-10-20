from django import forms

from child_health.repository import ChildHealthRecordRepository
from maternal.forms.maternal_identification_form import add_bootstrap_classes


class NewbornScreeningForm(forms.Form):
    
    """
        IMPORTANT NOTE:
    
            This has already been merged into BreastFeedingTypeForm.
        Keeping this here for reference in case we need to revert.
        
        Date: October 19, 2025    
    
    """
    
    referred_for_newborn_screening = forms.DateField(
        label="Date referred for newborn screening",
        required=True,
        widget=forms.DateInput(
            attrs={"type": "date", "class": "form-control"}),
        error_messages={'required': 'Please provide the date referred for newborn screening.'}
    )
    
    form_type = forms.CharField(widget=forms.HiddenInput(), initial="newborn_screening_form")
    

    def clean(self):
        cleaned_data = super().clean()
        return cleaned_data

    def __init__(self, chr_repo: ChildHealthRecordRepository, child_health_record_id: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
        self._repo = chr_repo
        self._chr_id = child_health_record_id
        self._screening_date = self._repo.fetch_new_born_screening_date_by_chr_id(self._chr_id)
        print(f"Newborn Screening Date Data: {self._screening_date}")
        if self._screening_date and isinstance(self._screening_date, list):
            if self._screening_date[0].get('referred_newborn_screening_date'):
                self.fields['referred_for_newborn_screening'].initial = self._screening_date[0]['referred_newborn_screening_date']
                self.fields['referred_for_newborn_screening'].widget.attrs['readonly'] = True
