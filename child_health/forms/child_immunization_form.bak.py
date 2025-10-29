from django import forms
from django.core.exceptions import ValidationError

from src.infra.repositories.child_health_record_repository import ChildHealthRecordRepository
from maternal.forms.maternal_identification_form import add_bootstrap_classes


class ChildImmunizationForm(forms.Form):
    """Immunization form with UI + server validation for allowed doses."""

    # --- BCG ---
    bcg_24hr = forms.BooleanField(label="BCG 24hr", required=False)
    bcg_1st  = forms.BooleanField(label="BCG 1st",  required=False)
    bcg_2nd  = forms.BooleanField(label="BCG 2nd",  required=False)
    bcg_3rd  = forms.BooleanField(label="BCG 3rd",  required=False)

    # --- Hep BV ---
    hepbv_24hr = forms.BooleanField(label="Hep. BV 24hr", required=False)
    hepbv_1st  = forms.BooleanField(label="Hep. BV 1st",  required=False)
    hepbv_2nd  = forms.BooleanField(label="Hep. BV 2nd",  required=False)
    hepbv_3rd  = forms.BooleanField(label="Hep. BV 3rd",  required=False)

    # --- PCV ---
    pcv_24hr = forms.BooleanField(label="PCV 24hr", required=False)
    pcv_1st  = forms.BooleanField(label="PCV 1st",  required=False)
    pcv_2nd  = forms.BooleanField(label="PCV 2nd",  required=False)
    pcv_3rd  = forms.BooleanField(label="PCV 3rd",  required=False)

    # --- OPV ---
    opv_24hr = forms.BooleanField(label="OPV 24hr", required=False)
    opv_1st  = forms.BooleanField(label="OPV 1st",  required=False)
    opv_2nd  = forms.BooleanField(label="OPV 2nd",  required=False)
    opv_3rd  = forms.BooleanField(label="OPV 3rd",  required=False)

    # --- AMV ---
    amv_24hr = forms.BooleanField(label="AMV 24hr", required=False)
    amv_1st  = forms.BooleanField(label="AMV 1st",  required=False)
    amv_2nd  = forms.BooleanField(label="AMV 2nd",  required=False)
    amv_3rd  = forms.BooleanField(label="AMV 3rd",  required=False)

    # --- Pentavalent ---
    pentavalent_24hr = forms.BooleanField(label="Pentavalent 24hr", required=False)
    pentavalent_1st  = forms.BooleanField(label="Pentavalent 1st",  required=False)
    pentavalent_2nd  = forms.BooleanField(label="Pentavalent 2nd",  required=False)
    pentavalent_3rd  = forms.BooleanField(label="Pentavalent 3rd",  required=False)
    
    form_type = forms.CharField(widget=forms.HiddenInput(), initial="child_immunization_form")

    # UI rules
    VACCINES_24HR_ONLY = ("bcg", "hepbv")                  # only 24hr allowed
    VACCINES_DOSES_1_3 = ("pcv", "opv", "amv", "pentavalent")  # only 1st–3rd allowed

    # Mapping helpers
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
        self._chr_repo = chr_repo
        self._chr_id = child_health_record_id

        # 1) Enforce UI (disable disallowed fields)
        self._disable_fields(self._disallowed_fields_for_ui())

        # 2) Prefill from DB payload → checkboxes
        rows = self._chr_repo.fetch_immunization_dates_matrix_by_chr_id(self._chr_id) or []
        self._apply_initials_from_payload(rows)

    # ---------- mapping payload → checkboxes ----------

    def _apply_initials_from_payload(self, rows: list[dict]) -> None:
        """
        For each record:
          - find field prefix via TYPE_PREFIX
          - for each date_* that is not None, mark the corresponding checkbox initial=True
        """
        for r in rows:
            prefix = self.TYPE_PREFIX.get((r.get("immunization_type_name") or "").upper())
            if not prefix:
                continue  # unknown type name

            for date_key, suffix in self.DATE_TO_SUFFIX.items():
                if r.get(date_key) is None:
                    continue
                field_name = f"{prefix}_{suffix}"
                if field_name in self.fields:
                    self.fields[field_name].initial = True  # date exists → checked

    # ---------- UI helpers ----------

    def _disallowed_fields_for_ui(self) -> tuple[str, ...]:
        disallowed = []
        # BCG/HEP BV: only 24hr → disable 1st–3rd
        for vac in self.VACCINES_24HR_ONLY:
            disallowed += [f"{vac}_1st", f"{vac}_2nd", f"{vac}_3rd"]
        # Others: disable 24hr
        for vac in self.VACCINES_DOSES_1_3:
            disallowed += [f"{vac}_24hr"]
        return tuple(disallowed)

    def _disable_fields(self, names: tuple[str, ...]) -> None:
        for name in names:
            if name in self.fields:
                self.fields[name].disabled = True
                self.fields[name].initial = False

    # ---------- server-side validation (defense-in-depth) ----------

    def clean(self):
        cleaned = super().clean()

        # BCG/HepBV: reject 1st–3rd if posted
        for vac in self.VACCINES_24HR_ONLY:
            for suf in ("1st", "2nd", "3rd"):
                fld = f"{vac}_{suf}"
                if cleaned.get(fld):
                    self.add_error(fld, ValidationError("Only the 24 hr dose is applicable for this vaccine."))

        # PCV/OPV/AMV/Pentavalent: reject 24hr if posted
        for vac in self.VACCINES_DOSES_1_3:
            fld = f"{vac}_24hr"
            if cleaned.get(fld):
                self.add_error(fld, ValidationError("24 hr dose is not applicable for this vaccine."))

        return cleaned
