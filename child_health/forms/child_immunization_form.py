from django import forms
from django.core.exceptions import ValidationError
from child_health.repository import ChildHealthRecordRepository
from maternal.forms.maternal_identification_form import add_bootstrap_classes


class ChildImmunizationForm(forms.Form):
    """Immunization form with date inputs for recording when vaccines were given."""

    date_widget = forms.DateInput(attrs={"type": "date", "class": "form-control"})

    # --- BCG ---
    bcg_24hr = forms.DateField(label="BCG 24hr", required=False, widget=date_widget)
    bcg_1st  = forms.DateField(label="BCG 1st",  required=False, widget=date_widget)
    bcg_2nd  = forms.DateField(label="BCG 2nd",  required=False, widget=date_widget)
    bcg_3rd  = forms.DateField(label="BCG 3rd",  required=False, widget=date_widget)

    # --- Hep BV ---
    hepbv_24hr = forms.DateField(label="Hep. BV 24hr", required=False, widget=date_widget)
    hepbv_1st  = forms.DateField(label="Hep. BV 1st",  required=False, widget=date_widget)
    hepbv_2nd  = forms.DateField(label="Hep. BV 2nd",  required=False, widget=date_widget)
    hepbv_3rd  = forms.DateField(label="Hep. BV 3rd",  required=False, widget=date_widget)

    # --- PCV ---
    pcv_24hr = forms.DateField(label="PCV 24hr", required=False, widget=date_widget)
    pcv_1st  = forms.DateField(label="PCV 1st",  required=False, widget=date_widget)
    pcv_2nd  = forms.DateField(label="PCV 2nd",  required=False, widget=date_widget)
    pcv_3rd  = forms.DateField(label="PCV 3rd",  required=False, widget=date_widget)

    # --- OPV ---
    opv_24hr = forms.DateField(label="OPV 24hr", required=False, widget=date_widget)
    opv_1st  = forms.DateField(label="OPV 1st",  required=False, widget=date_widget)
    opv_2nd  = forms.DateField(label="OPV 2nd",  required=False, widget=date_widget)
    opv_3rd  = forms.DateField(label="OPV 3rd",  required=False, widget=date_widget)

    # --- AMV ---
    amv_24hr = forms.DateField(label="AMV 24hr", required=False, widget=date_widget)
    amv_1st  = forms.DateField(label="AMV 1st",  required=False, widget=date_widget)
    amv_2nd  = forms.DateField(label="AMV 2nd",  required=False, widget=date_widget)
    amv_3rd  = forms.DateField(label="AMV 3rd",  required=False, widget=date_widget)

    # --- Pentavalent ---
    pentavalent_24hr = forms.DateField(label="Pentavalent 24hr", required=False, widget=date_widget)
    pentavalent_1st  = forms.DateField(label="Pentavalent 1st",  required=False, widget=date_widget)
    pentavalent_2nd  = forms.DateField(label="Pentavalent 2nd",  required=False, widget=date_widget)
    pentavalent_3rd  = forms.DateField(label="Pentavalent 3rd",  required=False, widget=date_widget)

    form_type = forms.CharField(widget=forms.HiddenInput(), initial="child_immunization_form")

    # --- Vaccine validation rules ---
    VACCINES_24HR_ONLY = ("bcg", "hepbv")                   # only 24hr applicable
    VACCINES_DOSES_1_3 = ("pcv", "opv", "amv", "pentavalent")  # 1st–3rd applicable

    TYPE_PREFIX = {
        "BCG": "bcg",
        "HEP BV": "hepbv",
        "PCV": "pcv",
        "OPV": "opv",
        "AMV": "amv",
        "PENTAVALENT": "pentavalent",
    }
    DATE_TO_SUFFIX = {
        "date_24hr": "24hr",
        "date_1st":  "1st",
        "date_2nd":  "2nd",
        "date_3rd":  "3rd",
    }

    def __init__(self, chr_repo: ChildHealthRecordRepository, child_health_record_id: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
        self._repo = chr_repo
        self._chr_id = child_health_record_id

        # Disable irrelevant inputs (UI enforcement)
        self._disable_fields(self._disallowed_fields_for_ui())

        # Pre-fill from DB
        rows = self._repo.fetch_immunization_dates_matrix_by_chr_id(self._chr_id) or []
        self._prefill_dates_from_db(rows)

    # ---------- Helper: disable invalid fields ----------
    def _disallowed_fields_for_ui(self) -> tuple[str, ...]:
        disallowed = []
        # BCG/HepBV: disable 1st–3rd
        for vac in self.VACCINES_24HR_ONLY:
            disallowed += [f"{vac}_1st", f"{vac}_2nd", f"{vac}_3rd"]
        # PCV/OPV/AMV/Pentavalent: disable 24hr
        for vac in self.VACCINES_DOSES_1_3:
            disallowed += [f"{vac}_24hr"]
        return tuple(disallowed)

    def _disable_fields(self, names: tuple[str, ...]) -> None:
        for name in names:
            if name in self.fields:
                self.fields[name].disabled = True

    # ---------- Helper: prefill fields from DB ----------
    def _prefill_dates_from_db(self, rows: list[dict]) -> None:
        """
        Pre-fill fields with existing immunization dates from the database.
        Expects each row to have:
            - immunization_type_name (e.g. "BCG")
            - date_24hr, date_1st, date_2nd, date_3rd
        """
        for r in rows:
            prefix = self.TYPE_PREFIX.get((r.get("immunization_type_name") or "").upper())
            if not prefix:
                continue
            for date_key, suffix in self.DATE_TO_SUFFIX.items():
                date_value = r.get(date_key)
                if date_value:
                    field_name = f"{prefix}_{suffix}"
                    if field_name in self.fields:
                        self.fields[field_name].initial = date_value

    # ---------- Validation ----------
    def clean(self):
        cleaned = super().clean()

        # Validation: only 24hr allowed for BCG/HepBV
        for vac in self.VACCINES_24HR_ONLY:
            for suf in ("1st", "2nd", "3rd"):
                fld = f"{vac}_{suf}"
                if cleaned.get(fld):
                    self.add_error(fld, ValidationError("Only the 24hr dose is allowed for this vaccine."))

        # Validation: 24hr not allowed for PCV/OPV/AMV/Pentavalent
        for vac in self.VACCINES_DOSES_1_3:
            fld = f"{vac}_24hr"
            if cleaned.get(fld):
                self.add_error(fld, ValidationError("24hr dose is not applicable for this vaccine."))

        # Optional: chronological validation
        for vac in self.VACCINES_DOSES_1_3:
            first, second, third = (cleaned.get(f"{vac}_1st"), cleaned.get(f"{vac}_2nd"), cleaned.get(f"{vac}_3rd"))
            if first and second and second < first:
                self.add_error(f"{vac}_2nd", ValidationError("2nd dose cannot be before 1st dose."))
            if second and third and third < second:
                self.add_error(f"{vac}_3rd", ValidationError("3rd dose cannot be before 2nd dose."))

        return cleaned
