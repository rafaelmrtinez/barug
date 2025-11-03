from django import forms

from maternal.forms.maternal_identification_form import add_bootstrap_classes

class PrenatalFollowUpFormSet(forms.Form):
    """
    Single inputs-only row matching the sheet:
    DATE | AOG | WT | BP | FINDINGS (Leopold's Maneuver) | NOTES
    """
    date = forms.DateField(
        required=False,
        label="Date",
        input_formats=["%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y"],
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    aog = forms.CharField(
        required=False,
        label="AOG",
        max_length=16,
        help_text="e.g., 28 or 28+3",
    )

    wt_kg = forms.DecimalField(
        required=False,
        label="WT (kg)",
        max_digits=5,
        decimal_places=2,
        min_value=0,
        widget=forms.NumberInput(attrs={"step": "0.1"}),
    )

    bp = forms.CharField(
        required=False,
        label="BP",
        max_length=7,
        help_text="e.g., 120/80",
    )

    findings = forms.CharField(
        required=False,
        label="Findings (Leopold’s Maneuver)",
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    notes = forms.CharField(
        required=False,
        label="Notes (Lab results, complaints, advises)",
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    # Accept custom kwargs so the formset can pass these safely
    def __init__(self, *args, mhr_repository=None, maternal_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
        self._mhr_repository = mhr_repository
        self._maternal_id = maternal_id