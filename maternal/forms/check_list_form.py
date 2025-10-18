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