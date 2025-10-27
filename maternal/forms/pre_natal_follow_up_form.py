from django import forms

from typing import Optional
from maternal.forms.maternal_identification_form import add_bootstrap_classes
from maternal.repository import MaternalHealthRecordRepository
from maternal.forms.form_utils import FormUtils


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
    aog_weeks = forms.IntegerField(
        required=False,
        label="AOG (weeks)",
        min_value=0,
        max_value=52,
        widget=forms.NumberInput(attrs={"step": "1", "inputmode": "numeric", "min": "0", "max": "52"}),
        help_text="Whole weeks, e.g. 28",
        error_messages={
            'invalid': 'Enter whole weeks as a number (e.g. 28).',
            'min_value': 'Weeks cannot be negative.',
            'max_value': 'Weeks cannot exceed 52.',
        },
    )
    aog_days = forms.IntegerField(
        required=False,
        label="AOG (days)",
        min_value=0,
        max_value=6,
        widget=forms.NumberInput(attrs={"step": "1", "inputmode": "numeric", "min": "0", "max": "6"}),
        help_text="Extra days (0–6)",
        error_messages={
            'invalid': 'Enter days as a whole number between 0 and 6.',
            'min_value': 'Days cannot be negative.',
            'max_value': 'Days must be between 0 and 6.',
        },
    )
    wt_kg = forms.FloatField(
        required=False,
        label="WT (kg)",
        min_value=0.0,
        widget=forms.NumberInput(attrs={"step": "0.1", "inputmode": "decimal", "min": "0"}),
        help_text="Weight in kilograms (e.g. 54.3)",
        error_messages={
            'invalid': 'Enter a valid weight (numbers only).',
            'min_value': 'Weight must be zero or positive.',
        },
    )
    bp_systolic = forms.IntegerField(
        required=False,
        label="BP (Systolic)",
        min_value=0,
        max_value=300,
        widget=forms.NumberInput(attrs={"step": "1", "inputmode": "numeric", "min": "0", "max": "300"}),
        help_text="e.g., 120",
        error_messages={
            'invalid': 'Enter systolic pressure as a whole number (e.g. 120).',
            'min_value': 'Systolic must be zero or positive.',
            'max_value': 'Systolic value seems too large.',
        },
    )
    bp_diastolic = forms.IntegerField(
        required=False,
        label="BP (Diastolic)",
        min_value=0,
        max_value=200,
        widget=forms.NumberInput(attrs={"step": "1", "inputmode": "numeric", "min": "0", "max": "200"}),
        help_text="e.g., 80",
        error_messages={
            'invalid': 'Enter diastolic pressure as a whole number (e.g. 80).',
            'min_value': 'Diastolic must be zero or positive.',
            'max_value': 'Diastolic value seems too large.',
        },
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
        self._role_norm = (role or "").strip().lower()

        if self._role_norm in self.BASIC_INFO_PERMS:
            self.fields["findings"].disabled = True
            self.fields["notes"].disabled = True
            self.fields["findings"].initial = "TBD"
            self.fields["notes"].initial = "TBD"
        elif self._role_norm not in self.FINDINGS_AND_NOTES_PERMS:
            self.fields["date"].disabled = True
            self.fields["aog_weeks"].disabled = True
            self.fields["aog_days"].disabled = True
            self.fields["wt_kg"].disabled = True
            self.fields["bp_systolic"].disabled = True
            self.fields["bp_diastolic"].disabled = True

    def clean(self):
        cleaned_data = super().clean()

        # Sanitize text fields and reject emojis / non-printable characters.
        for field_name, label in (('findings', "Findings"), ('notes', "Notes")):
            # If field is disabled (read-only), skip server-side sanitization
            field_obj = self.fields.get(field_name)
            if field_obj and getattr(field_obj, 'disabled', False):
                continue

            value = cleaned_data.get(field_name)
            if value is None:
                continue

            normalized, err = FormUtils.sanitize_text(value, label)
            if err:
                self.add_error(field_name, err)
                return cleaned_data

            # store normalized value back
            cleaned_data[field_name] = normalized

        # If the form was submitted by a Barangay Health Worker (BHW),
        # require all basic measurement fields to be present. Notes and
        # findings are intentionally excluded because BHWs only fill the
        # basic info block.
        if self.is_bound and (self._role_norm in self.BASIC_INFO_PERMS):
            required_fields = [
                'aog_weeks',
                'aog_days',
                'wt_kg',
                'bp_systolic',
                'bp_diastolic',
            ]

            missing_labels = []
            for fname in required_fields:
                # Consider empty string or None as missing
                val = cleaned_data.get(fname)
                if val in (None, ""):
                    field_obj = self.fields.get(fname)
                    missing_labels.append(getattr(field_obj, 'label', fname))

            if missing_labels:
                # Friendly non-field error listing the missing fields
                msg = (
                    "As a Barangay Health Worker, please fill out the following fields: "
                    + ", ".join(missing_labels)
                    + "."
                )
                # Attach as a non-field error so the UI can show a single message
                self.add_error(None, msg)
                return cleaned_data

        return cleaned_data
            