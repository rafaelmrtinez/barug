import datetime
from django import forms

from maternal.forms.maternal_identification_form import add_bootstrap_classes
from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository


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
        
        # require at least one TT date (TT1..TT5 or FIM)
        all_fields = list(self.LABEL_TO_FIELD.values()) + ['fim_date']
        if not any(cleaned_data.get(field) for field in all_fields):
            raise forms.ValidationError("At least one Tetanus Toxoid date must be provided.")

        # Build mapping field -> dose number and collect existing and submitted info
        field_to_number = {
            'tt1_date': 1,
            'tt2_date': 2,
            'tt3_date': 3,
            'tt4_date': 4,
            'tt5_date': 5,
            'fim_date': 6,
        }

        existing_numbers = set(self.existing_tt_by_number.keys()) if getattr(self, 'existing_tt_by_number', None) is not None else set(self.existing_tt_by_number.keys())
        # existing_dates: set of date objects already recorded
        existing_dates = set()
        for info in getattr(self, 'existing_tt_by_number', {}).values():
            dt = info.get('date_given')
            if dt is not None:
                existing_dates.add(dt)

        # If all doses 1..6 are already present in DB, disallow further entries
        if existing_numbers >= set(range(1, 7)):
            raise forms.ValidationError("All Tetanus Toxoid doses (TT1..TT5, FIM) have already been recorded for this patient; unable to add more.")

        submitted_numbers = set()
        submitted_dates = {}
        for field_name, num in field_to_number.items():
            val = cleaned_data.get(field_name)
            if val is not None:
                submitted_numbers.add(num)
                submitted_dates[num] = val

        # If any dose other than TT1 is submitted but TT1 is neither in DB nor in submission, require TT1
        if any(n != 1 for n in submitted_numbers) and 1 not in existing_numbers and 1 not in submitted_numbers:
            raise forms.ValidationError("TT1 date is required if any other TT date is provided.")

        # # Prevent re-entering a dose that's already recorded
        # for num in list(submitted_numbers):
        #     if num in existing_numbers:
        #         # get existing date for that dose
        #         info = self.existing_tt_by_number.get(num, {})
        #         existing_date = info.get('date_given')
        #         field_name = next(k for k, v in field_to_number.items() if v == num)
        #         self.add_error(field_name, f"TT{num} has already been recorded on {existing_date}. To change it, edit the existing record.")

        # Ensure submitted dates do not duplicate any existing recorded date
        # Note: if the submitted date equals the existing recorded date for the SAME dose
        # (i.e. user left the field unchanged), treat that as not a *new* entry and do not
        # raise a duplicate-date error. Only raise when the submitted date matches a date
        # already used by another dose or when the user is attempting to change an already
        # recorded dose (submit a different date for a dose that already exists).
        for num, dt in submitted_dates.items():
            # If this dose already exists in DB
            if num in existing_numbers:
                existing_info = self.existing_tt_by_number.get(num, {})
                existing_date_for_same_dose = existing_info.get('date_given')
                if dt == existing_date_for_same_dose:
                    # User left the date unchanged for an already-recorded dose; ignore
                    continue
                else:
                    # User is attempting to change an already-recorded dose — instruct them to edit
                    field_name = next(k for k, v in field_to_number.items() if v == num)
                    self.add_error(field_name, f"TT{num} has already been recorded on {existing_date_for_same_dose}. To change it, edit the existing record.")
                    # skip further duplicate-date checks for this field
                    continue

            # For new doses, ensure their date doesn't clash with any already-recorded date
            if dt in existing_dates:
                field_name = next(k for k, v in field_to_number.items() if v == num)
                self.add_error(field_name, f"A tetanus dose has already been recorded on {dt}. Please choose a different date.")

        # Ensure submitted dates are unique among themselves
        if len(submitted_dates.values()) != len(set(submitted_dates.values())):
            # find duplicates and add generic error
            raise forms.ValidationError("Please ensure submitted TT dates are unique — duplicate dates were provided.")

        # Ensure no skipped doses: for each submitted dose, all prior doses must exist either in DB or be submitted
        combined = existing_numbers.union(submitted_numbers)
        for num in sorted(submitted_numbers):
            for prior in range(1, num):
                if prior not in combined:
                    field_name = next(k for k, v in field_to_number.items() if v == num)
                    self.add_error(field_name, f"Cannot record TT{num} before TT{prior} is recorded. Please record earlier doses first.")

        # Ensure chronological order: each subsequent dose date must be on or after the previous dose date
        # Build combined dates mapping (prefer submitted date over existing)
        combined_dates = {}
        for n in range(1, 7):
            if n in submitted_dates:
                combined_dates[n] = submitted_dates[n]
            elif n in self.existing_tt_by_number:
                combined_dates[n] = self.existing_tt_by_number[n].get('date_given')
            else:
                combined_dates[n] = None

        for n in range(2, 7):
            prev = combined_dates.get(n-1)
            curr = combined_dates.get(n)
            if prev is not None and curr is not None:
                if curr < prev:
                    field_name = next(k for k, v in field_to_number.items() if v == n)
                    self.add_error(field_name, f"TT{n} date ({curr}) cannot be earlier than TT{n-1} date ({prev}). Please correct the dates.")
        
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