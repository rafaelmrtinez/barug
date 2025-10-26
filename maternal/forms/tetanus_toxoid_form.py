import datetime
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
    
    form_type = forms.CharField(initial="tetanus_toxoid", widget=forms.HiddenInput(
        attrs={'id': 'tt_form'}
    ))
    
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
        self._mhr_repo = mhr_repo
        self._mhr_id = mhr_id

        # fetch existing TT records for this maternal record
        self._existing_data = self._mhr_repo.fetch_maternal_tt_by_mhr_id(self._mhr_id) or []

        # Prefer ordering by record id (tt_id) to avoid date display inaccuracies.
        # Fall back to date_given if tt_id is not present.
        try:
            def sort_key(r):
                if r.get("tt_id") is not None:
                    return (int(r.get("tt_id")), datetime.date.min)
                return (0, r.get("date_given") or datetime.date.min)

            self._existing_data = sorted(self._existing_data, key=sort_key)
        except Exception:
            # if sorting fails, keep original order
            pass

        # map tt type name to numeric sequence (TT1..TT5 -> 1..5, FIM -> 6)
        TYPE_TO_INDEX = {"TT1": 1, "TT2": 2, "TT3": 3, "TT4": 4, "TT5": 5, "FIM": 6}

        # build ordered list of (tt_number, date_given, tt_id) from earliest insertion to latest
        self.received_tt_sequence = []
        self.existing_tt_by_number = {}  # tt_number -> {'tt_id': ..., 'date_given': ...}
        for row in self._existing_data:
            tt_name = (row.get("tt_type_name") or "").upper()
            date_given = row.get("date_given")
            record_id = row.get("tt_id")
            tt_number = TYPE_TO_INDEX.get(tt_name)
            if tt_number:
                # keep the sequence in insertion order (sorted above)
                self.received_tt_sequence.append((tt_number, date_given, record_id))
                # store last seen info for this tt_number (overwrites with later insertion)
                self.existing_tt_by_number[tt_number] = {"tt_id": record_id, "date_given": date_given}

        # determine the last recorded TT based on insertion order (last element in sequence)
        if self.received_tt_sequence:
            last_number, last_date, last_record_id = self.received_tt_sequence[-1]
            self._last_tt_number = last_number
            self._last_tt_date = last_date
            self._last_tt_record_id = last_record_id
            # reverse lookup for name (e.g. 1 -> 'TT1', 6 -> 'FIM')
            self._last_tt_name = next((k for k, v in TYPE_TO_INDEX.items() if v == last_number), None)
        else:
            self._last_tt_number = None
            self._last_tt_date = None
            self._last_tt_name = None
            self._last_tt_record_id = None

        # populate form fields' initial values from existing records (use tt_id ordering)
        for tt_num, info in self.existing_tt_by_number.items():
            if tt_num == 6:
                field_name = "fim_date"
            else:
                field_name = f"tt{tt_num}_date"
            if field_name in self.fields:
                # ensure date object or None
                self.fields[field_name].initial = info.get("date_given")

        # optional: expose last recorded date and id on the form instance for templates
        self.last_recorded_tt_date = self._last_tt_date
        self.last_recorded_tt_number = self._last_tt_number
        self.last_recorded_tt_record_id = self._last_tt_record_id

    def clean(self):
        cleaned_data = super().clean()
        
        # remove form_type before validation
        cleaned_data.pop('form_type', None)
        
        # require at least one TT date (TT1..TT5)
        if not any(cleaned_data.get(field) for field in self.LABEL_TO_FIELD.values()):
            raise forms.ValidationError("At least one Tetanus Toxoid date must be provided.")
        
        # if any TT provided, TT1 must be present
        if cleaned_data and not cleaned_data.get('tt1_date'):
            raise forms.ValidationError("TT1 date is required if any other TT date is provided.")
        
        # determine the last non-None entry among TT1..TT5 and FIM
        last_field = None
        last_value = None
        tt_id = None

        if cleaned_data.get('fim_date') is not None:
            last_field = 'fim_date'
            last_value = cleaned_data.get('fim_date')
            tt_id = 6
        else:
            for i in range(5, 0, -1):
                field_name = f"tt{i}_date"
                if cleaned_data.get(field_name) is not None:
                    last_field = field_name
                    last_value = cleaned_data.get(field_name)
                    tt_id = i
                    break

        # add last_entry (date value) and tt_id to cleaned_data
        cleaned_data['last_entry'] = last_value
        cleaned_data['tt_id'] = tt_id
        
        return cleaned_data