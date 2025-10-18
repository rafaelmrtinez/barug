from django import forms

from typing import Optional
from maternal.forms.maternal_identification_form import add_bootstrap_classes
from maternal.repository import MaternalHealthRecordRepository


class PrenatalFollowUpEntryForm(forms.Form):
    """
    Single inputs-only row:
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

    # Role policies — compare on lowercase
    BASIC_INFO_PERMS = {"bhw", "barangay health worker"}
    FINDINGS_AND_NOTES_PERMS  = {"midwife"}

    def __init__(self, *args, role: Optional[str] = None, mhr_repository: Optional[MaternalHealthRecordRepository] = None, maternal_id: Optional[int] = None, **kwargs):
        # Always call super first for Django forms
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
        self._mhr_repository = mhr_repository
        self._maternal_id = maternal_id
        role_norm = (role or "").strip().lower()

        if role_norm in self.BASIC_INFO_PERMS:
            self.fields["findings"].disabled = True
            self.fields["notes"].disabled = True
        elif role_norm not in self.FINDINGS_AND_NOTES_PERMS:
            self.fields["date"].disabled = True
            self.fields["aog"].disabled = True
            self.fields["wt_kg"].disabled = True
            self.fields["bp"].disabled = True