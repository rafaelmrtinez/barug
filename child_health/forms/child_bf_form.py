from django import forms

from child_health.repository import ChildHealthRecordRepository
from maternal.forms.maternal_identification_form import add_bootstrap_classes

class ChildBreastFeedingForm(forms.Form):
    
    for i in range(1, 6):
        locals()[f"exclusive_bf_check_{i}"] = forms.DateField(
            label=f"Exclusive BF check (Visit {i})",
            required=False,
            widget=forms.DateInput(
                attrs={"type": "date", "class": "form-control"}),
            error_messages={'required': f'Please provide the date for Exclusive BF check (Visit {i}).'}
        )
    del i

    def __init__(self, chr_repo: ChildHealthRecordRepository, child_id: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
        self._chrd_repo = chr_repo
        self._child_id = child_id
        
        """ 
        Load existing breastfeeding check dates for this child
        
        Breastfeeding Check Dates: [
            {'bbf_check_id': 106, 
            'check_date': datetime.date(2025, 10, 14), 
            'visit_id': 38, 
            'visit_no': 1, 
            'visit_date': None
            }, 
            {
                'bbf_check_id': 107, 
                'check_date': datetime.date(2025, 10, 14), 
                'visit_id': 43, 
                'visit_no': 2, 
                'visit_date': None
                }
            ]
        """
        bf_dates = self._chrd_repo.fetch_all_feeding_check_dates_by_person_id(self._child_id)
        print("Breastfeeding Check Dates:", bf_dates)
        # start with the last that and display it in bf_check_1 and so on
        if bf_dates:
            for index, record in enumerate(bf_dates):
                field_name = f"exclusive_bf_check_{index + 1}"
                if field_name in self.fields:
                    self.fields[field_name].initial = record['check_date']