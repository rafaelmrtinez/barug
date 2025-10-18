# maternal/forms/laboratory_form.py
from decimal import Decimal
from django import forms
from django.forms.widgets import ClearableFileInput

from maternal.forms.maternal_identification_form import add_bootstrap_classes
from maternal.forms.widgets import MultiImageInput
from maternal.repository import MaternalHealthRecordRepository


class LaboratoryForm(forms.Form):
    # --- Results ---
    urinalysis       = forms.CharField(required=False, label="Urinalysis")
    cbc              = forms.CharField(required=False, label="CBC")
    sgot_sgpt        = forms.CharField(required=False, label="SGOT/SGPT")
    creatinine_serum = forms.CharField(required=False, label="Creatinine serum")
    bua_bun          = forms.CharField(required=False, label="BUA/BUN")
    syphilis         = forms.CharField(required=False, label="Syphilis")
    hiv_test         = forms.CharField(required=False, label="HIV test")
    hepa_b           = forms.CharField(required=False, label="HEPA B")
    blood_typing     = forms.CharField(required=False, label="Blood typing")
    ogct_50g         = forms.DecimalField(required=False, label="OGCT (50g, 24–28 wks) mg/dL", max_digits=6, decimal_places=2)

    # --- Dates ---
    urinalysis_date       = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    cbc_date              = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    sgot_sgpt_date        = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    creatinine_serum_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    bua_bun_date          = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    syphilis_date         = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    hiv_test_date         = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    hepa_b_date           = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    blood_typing_date     = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    ogct_50g_date         = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))

    # --- Attachments (multi-image per test) ---
    img_widget = MultiImageInput(attrs={"multiple": True, "accept": "image/*"})

    urinalysis_images       = forms.ImageField(required=False, widget=img_widget, label="Attachments")
    cbc_images              = forms.ImageField(required=False, widget=img_widget, label="Attachments")
    sgot_sgpt_images        = forms.ImageField(required=False, widget=img_widget, label="Attachments")
    creatinine_serum_images = forms.ImageField(required=False, widget=img_widget, label="Attachments")
    bua_bun_images          = forms.ImageField(required=False, widget=img_widget, label="Attachments")
    syphilis_images         = forms.ImageField(required=False, widget=img_widget, label="Attachments")
    hiv_test_images         = forms.ImageField(required=False, widget=img_widget, label="Attachments")
    hepa_b_images           = forms.ImageField(required=False, widget=img_widget, label="Attachments")
    blood_typing_images     = forms.ImageField(required=False, widget=img_widget, label="Attachments")
    ogct_50g_images         = forms.ImageField(required=False, widget=img_widget, label="Attachments")

    def __init__(self, mhr_repo: MaternalHealthRecordRepository, mhr_id: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)

        data = mhr_repo.fetch_latest_laboratory_results_by_mhr_id(int(mhr_id))
        if not data:
            return
        row = data[0] if isinstance(data, list) else data

        value_map = {
            "urinalysis":            row.get("urinalysis_result"),
            "cbc":                   row.get("cbc_result"),
            "sgot_sgpt":             row.get("sgot_sgpt_result"),
            "creatinine_serum":      row.get("creatinine_serum_result"),
            "bua_bun":               row.get("bua_bun_result"),
            "syphilis":              row.get("syphilis_result"),
            "hiv_test":              row.get("hiv_result"),
            "hepa_b":                row.get("hepa_b_result"),
            "blood_typing":          row.get("blood_typing_result"),
            "ogct_50g":              row.get("ogct_50g_result"),
            "urinalysis_date":       row.get("urinalysis_date"),
            "cbc_date":              row.get("cbc_date"),
            "sgot_sgpt_date":        row.get("sgot_sgpt_date"),
            "creatinine_serum_date": row.get("creatinine_serum_date"),
            "bua_bun_date":          row.get("bua_bun_date"),
            "syphilis_date":         row.get("syphilis_date"),
            "hiv_test_date":         row.get("hiv_date"),
            "hepa_b_date":           row.get("hepa_b_date"),
            "blood_typing_date":     row.get("blood_typing_date"),
            "ogct_50g_date":         row.get("ogct_50g_date"),
        }

        for name, val in value_map.items():
            if val in (None, ""):
                continue
            if name == "ogct_50g":
                try:
                    self.fields[name].initial = Decimal(str(val))
                except Exception:
                    self.fields[name].initial = val
            else:
                self.fields[name].initial = val
