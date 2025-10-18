from django import forms

from maternal.forms.maternal_identification_form import add_bootstrap_classes
from maternal.repository import MaternalHealthRecordRepository


class TetanusToxoidForm(forms.Form):
    # Tetanus toxoid dates
    tt1_date = forms.DateField(required=False, widget=forms.DateInput(
        attrs={'type': 'date'}), label="TT1")
    tt2_date = forms.DateField(required=False, widget=forms.DateInput(
        attrs={'type': 'date'}), label="TT2")
    tt3_date = forms.DateField(required=False, widget=forms.DateInput(
        attrs={'type': 'date'}), label="TT3")
    tt4_date = forms.DateField(required=False, widget=forms.DateInput(
        attrs={'type': 'date'}), label="TT4")
    tt5_date = forms.DateField(required=False, widget=forms.DateInput(
        attrs={'type': 'date'}), label="TT5")
    fim_date = forms.DateField(required=False, widget=forms.DateInput(
        attrs={'type': 'date'}), label="FIM")
    
    LABEL_TO_FIELD  = {
            "TT1": "tt1_date",
            "TT2": "tt2_date",
            "TT3": "tt3_date",
            "TT4": "tt4_date",
            "TT5": "tt5_date",
        }
    
    def __init__(self, mhr_repo: MaternalHealthRecordRepository, mhr_id: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)

        # Fetch rows like:
        # [{'maternal_record_id': 1, 'dose_label': 'TT1', 'date_given': date(2025,9,15), 'fim_level': 1, ...}, ...]
        tt_rows = mhr_repo.fetch_maternal_tt_by_mhr_id(mhr_id) or []

        # Set TT1..TT5
        for row in tt_rows:
            label = (row.get("dose_label") or "").upper()
            date_given = self.__to_iso(row.get("date_given"))
            field_name = self.LABEL_TO_FIELD.get(label)
            if field_name and date_given:
                self.fields[field_name].initial = date_given

        # Set FIM = date of the highest fim_level present
        if tt_rows:
            last = max(
                (r for r in tt_rows if r.get("fim_level") is not None),
                key=lambda r: r.get("fim_level", 0),
                default=None,
            )
            if last and last.get("date_given"):
                self.fields["fim_date"].initial = self.__to_iso(last["date_given"])

    def __to_iso(self, d):
        # Map dose_label -> ISO date string
        return d.isoformat() if hasattr(d, "isoformat") else (str(d) if d else None)