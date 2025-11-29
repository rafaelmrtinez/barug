from django import forms
from datetime import datetime, date

from src.infra.repositories.child_health_record_repository import ChildHealthRecordRepository
from maternal.forms.maternal_identification_form import add_bootstrap_classes
from maternal.forms.form_utils import FormUtils
from src.infra.utilities.custom_date_time_util import DateAndTimeUtility

class BirthAndSupplentationForm(forms.Form):
    # Immunization fields: these map to a table, so use per field for each dose.
    # child_protected_at_birth = forms.CharField(label="Child protected at birth", required=False)
    data_assessed = forms.CharField(
        label="Date assessed", 
        required=False, 
        widget=forms.DateInput(
            attrs={"type": "date", "class": "form-control"}), 
        error_messages={'required': 'Please provide the date assessed.'})
    tt_status_mother = forms.CharField(label="Tetanus Toxoid (TT) Status", required=False)
    anemia_2_59_seen = forms.CharField(
        label="Anemic children 2-59 mos. Seen", required=False, widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
    anemia_2_59_given_iron = forms.CharField(
        label="Anemic children 2-59 mos. Given iron", required=False, widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
    birth_weight = forms.DecimalField(
        label="Birth weight", 
        required=False, 
        max_digits=5, 
        decimal_places=2,
        error_messages={'required': 'Please provide the birth weight.'})
    low_birth_weight = forms.BooleanField(
        label="If low birth weight", required=False)
    birth_wt_seen = forms.CharField(label="2-6 mos. Seen", required=False, widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
    birth_wt_given_iron = forms.CharField(label="2-6 mos. Given iron", required=False, widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))

    form_type = forms.CharField(widget=forms.HiddenInput(attrs={'id': 'id_form_type_bs'}), initial='birth_and_supplementation_form')

    def __init__(
        self, 
        chr_repo: ChildHealthRecordRepository, 
        child_health_record_id, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
        self._repo = chr_repo
        tt_status_mother = self._repo.fetch_mother_tt_type(child_health_record_id)
        self._existing_data = self._repo.fetch_child_screening_package(child_health_record_id)       
        # If existing data present, populate initial values and make fields readonly
        if self._existing_data and isinstance(self._existing_data, dict):
            ex = self._existing_data
            # date assessed
            da = ex.get('date_assessed')
            if isinstance(da, datetime):
                da = da.date()
            if isinstance(da, date):
                self.fields['data_assessed'].initial = da
                self.fields['data_assessed'].widget.attrs['readonly'] = True

            # birth weight
            bw = ex.get('birth_weight')
            if bw is not None:
                self.fields['birth_weight'].initial = bw
                # keep as readonly (not disabled) so value posts
                self.fields['birth_weight'].widget.attrs['readonly'] = True

            # anemia fields
            a_seen = ex.get('anemic_2_59_seen_date')
            if isinstance(a_seen, datetime):
                a_seen = a_seen.date()
            if isinstance(a_seen, date):
                self.fields['anemia_2_59_seen'].initial = a_seen
                self.fields['anemia_2_59_seen'].widget.attrs['readonly'] = True

            a_given = ex.get('anemic_2_59_given_iron_date')
            if isinstance(a_given, datetime):
                a_given = a_given.date()
            if isinstance(a_given, date):
                self.fields['anemia_2_59_given_iron'].initial = a_given
                self.fields['anemia_2_59_given_iron'].widget.attrs['readonly'] = True

            # 2-6 mos fields
            bw_seen = ex.get('seen_2_6_mos_date')
            if isinstance(bw_seen, datetime):
                bw_seen = bw_seen.date()
            if isinstance(bw_seen, date):
                self.fields['birth_wt_seen'].initial = bw_seen
                self.fields['birth_wt_seen'].widget.attrs['readonly'] = True

            bw_given = ex.get('given_2_6_mos_date')
            if isinstance(bw_given, datetime):
                bw_given = bw_given.date()
            if isinstance(bw_given, date):
                self.fields['birth_wt_given_iron'].initial = bw_given
                self.fields['birth_wt_given_iron'].widget.attrs['readonly'] = True

        # populate TT status from repository result if present
        if tt_status_mother:
            try:
                # tt_status_mother may be a list or dict
                if isinstance(tt_status_mother, list) and tt_status_mother:
                    tt = tt_status_mother[0]
                elif isinstance(tt_status_mother, dict):
                    tt = tt_status_mother
                else:
                    tt = None
                if tt:
                    name = tt.get('tt_type_name') or tt.get('tt_type') or str(tt.get('tt_type_id'))
                    if name:
                        sanitized, err = FormUtils.sanitize_text(str(name), "TT Status")
                        self.fields['tt_status_mother'].initial = sanitized if not err else str(name)
            except Exception:
                pass
        self.fields['tt_status_mother'].widget.attrs['readonly'] = True