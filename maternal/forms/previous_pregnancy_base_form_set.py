from django.forms import BaseFormSet, formset_factory

from maternal.forms.previous_pregnancy_form import PreviousPregnancyForm

class PreviousPregnancyBaseFormSet(BaseFormSet):
    def __init__(self, *args, mhr_repository=None, maternal_id=None, **kwargs):
        super().__init__(*args, **kwargs)

PreviousPregnancyFormSet = formset_factory(
    PreviousPregnancyForm,
    formset=PreviousPregnancyBaseFormSet,
    extra=0,
    can_delete=True,
)
