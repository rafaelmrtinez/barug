from django import forms
from django.forms import formset_factory
from maternal.constants import DELIVERY_TYPE_CHOICES, GENDER_CHOICES, OUTCOME_CHOICES
from maternal.forms.maternal_identification_form import add_bootstrap_classes

class PreviousPregnancyForm(forms.Form):
    delivery_date   = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}), label="Date of delivery")
    outcome         = forms.ChoiceField(choices=OUTCOME_CHOICES, required=False)
    delivery_type   = forms.ChoiceField(choices=DELIVERY_TYPE_CHOICES, required=False, label="Type of delivery")
    baby_weight_kg  = forms.DecimalField(required=False, label="Baby's weight (kg)", max_digits=5, decimal_places=2)
    gender          = forms.ChoiceField(choices=GENDER_CHOICES, required=False)
    ballard_score   = forms.IntegerField(required=False, label="Ballard score")
    apgar_score     = forms.IntegerField(required=False, label="Apgar score")

    # Accept custom kwargs so formset can pass them safely
    def __init__(self, *args, mhr_repository=None, maternal_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)


PreviousPregnancyFormSet = formset_factory(
    PreviousPregnancyForm,
    extra=0,
    can_delete=True,
)
