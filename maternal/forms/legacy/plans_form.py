from django import forms

from maternal.forms.maternal_identification_form import add_bootstrap_classes
from maternal.repository import MaternalHealthRecordRepository


class PlanForm(forms.Form):
    # Plans
    plan_place_of_delivery = forms.CharField(required=False)
    plan_newborn_screening = forms.BooleanField(
        required=False, label="Plan for newborn screening")
    
    def __init__(self, mhr_repo: MaternalHealthRecordRepository, mhr_id: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
        place_for_delivery_plan = mhr_repo.fetch_delivery_plan_by_mhr_id(int(mhr_id))
        print(f"Delivery plan data: {place_for_delivery_plan}")
        if place_for_delivery_plan:
            self.fields['plan_place_of_delivery'].initial = place_for_delivery_plan[0].get('place_of_delivery_plan', '')
            self.fields['plan_newborn_screening'].initial = place_for_delivery_plan[0].get('new_born_screening_plan', False)