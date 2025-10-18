from django import forms

from child_health.repository import ChildHealthRecordRepository
from maternal.forms.maternal_identification_form import add_bootstrap_classes


class NewbornScreeningForm(forms.Form):
    referred_for_newborn_screening = forms.DateField(
        label="Date referred for newborn screening",
        required=True,
        widget=forms.DateInput(
            attrs={"type": "date", "class": "form-control"}),
        error_messages={'required': 'Please provide the date referred for newborn screening.'}
    )
    
    type_of_feeding = forms.ChoiceField(
        label="Type of Feeding", 
        required=True, 
        choices=[],
        error_messages={'required': 'Please select a type of feeding.'})

    def __init__(self, chr_repo: ChildHealthRecordRepository, child_id: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
        
        """ 
            Expected Data:
            Newborn Screening Data: {
                'child_record_id': 5, 
                'visit_id': 43, 
                'visit_no': 2, 
                'visit_date': None, 
                'referred_nbs_date': datetime.date(2025, 10, 14), 
                'feeding_type_id': 1, 
                'feeding_type_name': 'EXCLUSIVE BREASTFEEDING'
                }
        """
        newborn_screening_data = chr_repo.fetch_child_newborn_screening_by_person_id(child_id)
        print("Newborn Screening Data:", newborn_screening_data)
        feeding_types = chr_repo.fetch_all_feeding_type()
        
        self.fields['type_of_feeding'].choices = [('', 'Select Feeding Type')] + [(ft['feeding_type_id'], ft['feeding_type_name']) for ft in feeding_types]
        
        if newborn_screening_data:
            self.fields['referred_for_newborn_screening'].initial = newborn_screening_data.get('referred_nbs_date')
            self.fields['type_of_feeding'].initial = newborn_screening_data.get('feeding_type_id')