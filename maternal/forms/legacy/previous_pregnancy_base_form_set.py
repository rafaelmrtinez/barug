from django.forms import BaseFormSet, formset_factory

from maternal.forms.previous_pregnancy_form import PreviousPregnancyForm

class PreviousPregnancyBaseFormSet(BaseFormSet):
    def __init__(self, *args, mhr_repository=None, maternal_id=None, **kwargs):
        # If no initial provided, we can fetch and populate here
        if 'initial' not in kwargs and mhr_repository and maternal_id:
            person_id = mhr_repository.fetch_person_id_by_maternal_record_id(maternal_id)
            rows = mhr_repository.fetch_all_previous_pregnancies_by_person_id(person_id)

            init_list = []
            for r in rows:
                init_list.append({
                    "delivery_date":  r.get("date_of_delivery"),
                    "outcome":        r.get("outcome_type"),
                    "delivery_type":  r.get("delivery_type_id"),
                    "baby_weight_kg": r.get("baby_weight_kg"),
                    "gender":         r.get("baby_sex"),
                    "ballard_score":  r.get("ballard"),
                    "apgar_score":    r.get("apgar"),
                })
            kwargs['initial'] = init_list

        super().__init__(*args, **kwargs)

PreviousPregnancyFormSet = formset_factory(
    PreviousPregnancyForm,
    formset=PreviousPregnancyBaseFormSet,
    extra=0,
    can_delete=True,
)
