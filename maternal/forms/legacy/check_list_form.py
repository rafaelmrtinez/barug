# forms.py
from django import forms
import re

from maternal.constants import SYMPTOM_CHOICES
from maternal.forms.maternal_identification_form import add_bootstrap_classes
from maternal.repository import MaternalHealthRecordRepository


def _norm(s: str) -> str:
    """Normalize labels/names for loose matching."""
    if not s:
        return ''
    s = s.lower()
    s = s.replace('&', 'and')
    s = re.sub(r'[^a-z0-9\s]+', ' ', s)      # remove punctuation
    s = re.sub(r'\s+', ' ', s).strip()
    return s

class CheckListForm(forms.Form):
    symptoms = forms.MultipleChoiceField(
        required=False,
        choices=SYMPTOM_CHOICES,
        widget=forms.CheckboxSelectMultiple
    )
    preeclampsia_flag = forms.BooleanField(required=False, label="Preeclampsia")

    def __init__(self, mhr_repo: MaternalHealthRecordRepository, mhr_id: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)

        # Build lookup: normalized choice label -> key
        # SYMPTOM_CHOICES = [(key, label), ...]
        label_to_key = { _norm(label): key for key, label in SYMPTOM_CHOICES }

        # Fetch latest-visit checklist rows for this maternal record
        rows = mhr_repo.fetch_maternal_checklist_by_mhr_id(int(mhr_id))
        # Example row: {'checklist_name': 'ABNORMAL VAGINAL DISCHARGES', ...}

        selected_keys = []
        for r in rows or []:
            name = r.get('checklist_name') or ''
            k = label_to_key.get(_norm(name))
            if k:
                selected_keys.append(k)

        # Pre-check the boxes
        if selected_keys:
            self.fields['symptoms'].initial = selected_keys

        # (Optional) derive preeclampsia flag from selected symptoms
        # Example heuristic: set True if any of these are present.
        pe_keys = {
            'increased_bp', 'epigastric_pain', 'blurred_vision',
            'severe_headache', 'edema'
        }
        self.fields['preeclampsia_flag'].initial = any(k in pe_keys for k in selected_keys)
