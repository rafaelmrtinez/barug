from django import forms

from child_health.repository import ChildHealthRecordRepository
from maternal.forms.maternal_identification_form import add_bootstrap_classes

TYPE_KEYS = {
    'bcg': 'bcg',
    'hepbv': 'hepbv', 'hep b': 'hepbv', 'hepatitis b': 'hepbv', 'hep. bv': 'hepbv',
    'pcv': 'pcv',
    'opv': 'opv',
    'amv': 'amv',
    'pentavalent': 'pentavalent',
}

# Normalize many ways clinics write the stage names
STAGE_KEYS = {
    '24hr': '24hr', '24-hr': '24hr', '24 hours': '24hr', 'within 24 hours': '24hr', 'at birth': '24hr',
    '1st': '1st', 'first': '1st',
    '2nd': '2nd', 'second': '2nd',
    '3rd': '3rd', 'third': '3rd',
}

def _norm(s: str) -> str:
    return (s or '').strip().lower()

class ChildImmunizationForm(forms.Form):
    bcg_24hr = forms.BooleanField(label="BCG 24hr", required=False)
    bcg_1st = forms.BooleanField(label="BCG 1st", required=False)
    bcg_2nd = forms.BooleanField(label="BCG 2nd", required=False)
    bcg_3rd = forms.BooleanField(label="BCG 3rd", required=False)
    hepbv_24hr = forms.BooleanField(label="Hep. BV 24hr", required=False)
    hepbv_1st = forms.BooleanField(label="Hep. BV 1st", required=False)
    hepbv_2nd = forms.BooleanField(label="Hep. BV 2nd", required=False)
    hepbv_3rd = forms.BooleanField(label="Hep. BV 3rd", required=False)
    pcv_24hr = forms.BooleanField(label="PCV 24hr", required=False)
    pcv_1st = forms.BooleanField(label="PCV 1st", required=False)
    pcv_2nd = forms.BooleanField(label="PCV 2nd", required=False)
    pcv_3rd = forms.BooleanField(label="PCV 3rd", required=False)
    opv_24hr = forms.BooleanField(label="OPV 24hr", required=False)
    opv_1st = forms.BooleanField(label="OPV 1st", required=False)
    opv_2nd = forms.BooleanField(label="OPV 2nd", required=False)
    opv_3rd = forms.BooleanField(label="OPV 3rd", required=False)
    amv_24hr = forms.BooleanField(label="AMV 24hr", required=False)
    amv_1st = forms.BooleanField(label="AMV 1st", required=False)
    amv_2nd = forms.BooleanField(label="AMV 2nd", required=False)
    amv_3rd = forms.BooleanField(label="AMV 3rd", required=False)
    pentavalent_24hr = forms.BooleanField(
        label="Pentavalent 24hr", required=False)
    pentavalent_1st = forms.BooleanField(
        label="Pentavalent 1st", required=False)
    pentavalent_2nd = forms.BooleanField(
        label="Pentavalent 2nd", required=False)
    pentavalent_3rd = forms.BooleanField(
        label="Pentavalent 3rd", required=False)
    
    def __init__(self, chr_repo: ChildHealthRecordRepository, child_id: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)

        chr_id = chr_repo.fetch_child_record_id_by_person_id(child_id)
        rows = chr_repo.fetch_all_child_immunizations_by_chr_id(chr_id) or []
        print("Immunization Records:", rows)
        for r in rows:
            # accept either set of keys
            raw_type  = _norm(r.get("immunization_type_name")  or r.get("type_name"))
            raw_stage = _norm(r.get("immunization_stage_name") or r.get("stage_name"))

            # map type (substring match: 'hep b', 'hepatitis b', etc → 'hepbv')
            type_key = None
            for alias, canonical in TYPE_KEYS.items():
                if alias in raw_type:
                    type_key = canonical
                    break
            if not type_key:
                continue  # unknown type; skip

            # map stage (exact or substring)
            stage_key = STAGE_KEYS.get(raw_stage)
            if not stage_key:
                for alias, canonical in STAGE_KEYS.items():
                    if alias in raw_stage:
                        stage_key = canonical
                        break
            if not stage_key:
                continue  # unknown stage; skip

            field_name = f"{type_key}_{stage_key}"
            if field_name in self.fields:
                # mark checkbox as checked via initial
                self.initial[field_name] = True
