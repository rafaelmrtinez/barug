from django import forms
from datetime import datetime, date

from child_health.repository import ChildHealthRecordRepository
from maternal.forms.maternal_identification_form import add_bootstrap_classes
from maternal.forms.form_utils import FormUtils
from barug.utility.custom_date_time_util import DateAndTimeUtility

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

    def __init__(self, chr_repo: ChildHealthRecordRepository, child_health_record_id, *args, **kwargs):
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
                        self.fields['tt_status_mother'].widget.attrs['readonly'] = True
            except Exception:
                pass
    def clean(self):
        cleaned_data = super().clean()
        all_tt_types = self._repo.fetch_all_tt_types()


        # Helper: parse date-like inputs into date objects
        def normalize_date(value, field_label):
            if value is None or value == "":
                return None, None
            if isinstance(value, date):
                return value, None
            if isinstance(value, datetime):
                return value.date(), None
            if isinstance(value, str):
                parsed = DateAndTimeUtility.parse_date(value)
                if parsed:
                    return parsed, None
                return None, f"{field_label} must be a valid date in YYYY-MM-DD format."
            return None, f"{field_label} must be a valid date."

        # Normalize and validate date fields
        date_fields = {
            'data_assessed': 'Date assessed',
            'anemia_2_59_seen': 'Anemia (2-59 mos) seen date',
            'anemia_2_59_given_iron': 'Anemia (2-59 mos) given iron date',
            'birth_wt_seen': '2-6 mos seen date',
            'birth_wt_given_iron': '2-6 mos given iron date',
        }

        normalized = {}
        for fname, label in date_fields.items():
            val = cleaned_data.get(fname)
            nd, err = normalize_date(val, label)
            if err:
                self.add_error(fname, err)
                return cleaned_data
            normalized[fname] = nd

        # Normalize birth_weight
        bw = cleaned_data.get('birth_weight')
        if bw in (None, ''):
            bw_val = None
        else:
            try:
                # Keep as Decimal if provided by form; ensure non-negative
                if isinstance(bw, str):
                    bw_val = float(bw)
                else:
                    bw_val = float(bw)
                if bw_val < 0:
                    self.add_error('birth_weight', 'Birth weight cannot be negative.')
                    return cleaned_data
            except Exception:
                self.add_error('birth_weight', 'Enter a valid birth weight (numbers only).')
                return cleaned_data

        # Ensure required fields present: data_assessed, birth_weight, tt_status_mother
        if normalized['data_assessed'] is None:
            self.add_error('data_assessed', 'Please provide the date assessed.')
            return cleaned_data

        if bw_val is None:
            self.add_error('birth_weight', 'Please provide the birth weight.')
            return cleaned_data

        tt_val = cleaned_data.get('tt_status_mother')
        # sanitize tt_status_mother
        if tt_val in (None, ''):
            self.add_error('tt_status_mother', 'Please provide the mother\'s TT status.')
            return cleaned_data
        sanitized_tt, tt_err = FormUtils.sanitize_text(str(tt_val), 'TT status')
        if tt_err:
            self.add_error('tt_status_mother', tt_err)
            return cleaned_data

        # Map incoming TT status to an ID using all_tt_types from repository
        # Accept DB rows as list of tuples [(id, name), ...] or list of dicts [{'tt_type_id': id, 'tt_type_name': name}, ...]
        if not all_tt_types:
            self.add_error('tt_status_mother', 'TT types are unavailable. Please try again later.')
            return cleaned_data

        incoming_norm = (sanitized_tt or '').strip().upper()
        matched_id = None
        matched_name = None
        for row in all_tt_types:
            try:
                if isinstance(row, dict):
                    row_id = row.get('tt_type_id')
                    row_name = row.get('tt_type_name')
                elif isinstance(row, (list, tuple)):
                    if len(row) >= 2:
                        row_id = row[0]
                        row_name = row[1]
                    else:
                        continue
                else:
                    # unknown shape, skip
                    continue

                # Normalize DB name for comparison
                db_name_sanitized, _ = FormUtils.sanitize_text(str(row_name or ''), 'TT name')
                db_norm = (db_name_sanitized or str(row_name or '')).strip().upper()

                if db_norm == incoming_norm:
                    try:
                        matched_id = int(row_id)
                    except Exception:
                        # if id cannot be cast to int, skip
                        matched_id = None
                        continue
                    matched_name = db_name_sanitized or str(row_name)
                    break
            except Exception:
                # be resilient to malformed rows
                continue

        if matched_id is None:
            self.add_error('tt_status_mother', 'TT status does not match known types.')
            return cleaned_data

        # Prevent future dates for all provided dates
        try:
            ph_today = DateAndTimeUtility.parse_date(DateAndTimeUtility.get_current_date()) or date.today()
        except Exception:
            ph_today = date.today()

        for fname, dval in normalized.items():
            if dval is not None and dval > ph_today:
                self.add_error(fname, f"{date_fields[fname]} cannot be in the future.")
                return cleaned_data

        # If both anemia seen and given present, ensure given >= seen
        a_seen = normalized['anemia_2_59_seen']
        a_given = normalized['anemia_2_59_given_iron']
        if a_seen and a_given:
            if a_given < a_seen:
                self.add_error('anemia_2_59_given_iron', 'Given iron date cannot be before when anemia was seen.')
                return cleaned_data

        # If both birth_wt_seen and given present, ensure given >= seen
        bw_seen = normalized['birth_wt_seen']
        bw_given = normalized['birth_wt_given_iron']
        if bw_seen and bw_given:
            if bw_given < bw_seen:
                self.add_error('birth_wt_given_iron', 'Given iron date (2-6 mos) cannot be before when child was seen.')
                return cleaned_data

        # All validations passed — write normalized values back and sanitized tt
        cleaned_data['data_assessed'] = normalized['data_assessed']
        cleaned_data['anemia_2_59_seen'] = a_seen
        cleaned_data['anemia_2_59_given_iron'] = a_given
        cleaned_data['birth_wt_seen'] = bw_seen
        cleaned_data['birth_wt_given_iron'] = bw_given
        cleaned_data['birth_weight'] = bw_val
        cleaned_data['tt_status_mother'] = matched_name or sanitized_tt
        # Expose the mapped TT id for downstream processing
        cleaned_data['tt_id'] = matched_id

        return cleaned_data
