from django import forms

from child_health.repository import ChildHealthRecordRepository
from maternal.forms.maternal_identification_form import add_bootstrap_classes

class BreastFeedingTypeForm(forms.Form):
    form_type = forms.CharField(initial="bf_type_form", widget=forms.HiddenInput())
    
    type_of_feeding = forms.ChoiceField(
        label="Type of Feeding",
        required=True, 
        choices=[],
        error_messages={'required': 'Please select a type of feeding.'})
    
    def __init__(self, chr_repo: ChildHealthRecordRepository, child_health_record_id: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
        newborn_screening_data = chr_repo.fetch_child_newborn_screening_by_person_id(child_health_record_id)
        self.display_type_of_feeding_selections(chr_repo)
        if newborn_screening_data:
            self.fields['type_of_feeding'].initial = newborn_screening_data.get('feeding_type_id')
            self.fields['type_of_feeding'].widget.attrs['readonly'] = True
            
    def display_type_of_feeding_selections(self, chr_repo):
        feeding_types = chr_repo.fetch_all_feeding_type()
        self.fields['type_of_feeding'].choices = [('', 'Select Feeding Type')] + [(ft['feeding_type_id'], ft['feeding_type_name']) for ft in feeding_types]