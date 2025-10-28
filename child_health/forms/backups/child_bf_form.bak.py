from django import forms
from datetime import datetime, date

from barug.utility.custom_date_time_util import DateAndTimeUtility
from child_health.repository import ChildHealthRecordRepository
from maternal.forms.maternal_identification_form import add_bootstrap_classes
# Adjust this import path to where you placed the helper



class ChildBreastFeedingForm(forms.Form):

    type_of_feeding = forms.ChoiceField(
        label="Type of Feeding",
        required=True,
        choices=[],
        error_messages={'required': 'Please select a type of feeding.'},
    )

    # Visits 1..5 (we’ll map oldest -> 1, … newest -> 5)
    for i in range(1, 6):
        locals()[f"exclusive_bf_check_{i}"] = forms.DateField(
            label=f"Exclusive BF check (Visit {i})",
            required=False,
            widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            error_messages={
                'required': f'Please provide the date for Exclusive BF check (Visit {i}).'
            },
        )
    del i

    form_type = forms.CharField(initial="bf_feeding_form", widget=forms.HiddenInput())

    # -------------------- lifecycle --------------------

    def __init__(
        self,
        *args,
        chr_repo: ChildHealthRecordRepository | None = None,
        child_health_record_id: int | None = None,
        **kwargs,
    ):
        """
        `child_health_record_id` is passed to:
            chr_repo.fetch_child_details_bf_display_by_chr_id(child_health_record_id)
        which returns rows containing:
            bbf_check_id, check_date, child_record_id, visit_id,
            feeding_type_nwbrn_scrnng_id, latest_visit_id,
            feeding_type_id, feeding_type_name, referred_newborn_screening_date
        """
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)

        self._repo = chr_repo
        self._child_health_record_id = child_health_record_id

        # Today in Asia/Manila (for UI + server validation)
        self._today_ph_str = DateAndTimeUtility.get_current_date()  # "YYYY-MM-DD"
        self._today_ph = datetime.strptime(self._today_ph_str, "%Y-%m-%d").date()
    
        # Client-side guard: cap date pickers to today
        self._apply_max_date_on_widgets(self._today_ph_str)

        # Pull choices and hydrate data
        self.child_details = self._fetch_child_bf_details()
        
        self._setup_type_of_feeding_choices()
        self._populate_bf_checks_from_details(self.child_details)         # oldest -> newest
        # self._populate_type_of_feeding_from_details(self.child_details)   # latest visit
        self._apply_succession_lock()
        
        for i in range(5):
            if self.fields[f"exclusive_bf_check_{i+1}"].initial:
                self.fields[f"exclusive_bf_check_{i+1}"].widget.attrs['readonly'] = True

    # -------------------- clean / validation --------------------

    def clean(self):
        cleaned = super().clean()

        # A) No future dates (Asia/Manila)
        self._guard_no_future_dates(cleaned)

        # B) Enforce succession (cannot fill visit i without i-1)
        for i in range(2, 6):
            prev = cleaned.get(f"exclusive_bf_check_{i-1}")
            curr = cleaned.get(f"exclusive_bf_check_{i}")
            if curr and not prev:
                self.add_error(
                    f"exclusive_bf_check_{i}",
                    f"Please fill Exclusive BF check (Visit {i-1}) first.",
                )

        # C) Latest provided date client posted (5..1)
        last = None
        count = 5 # just for clarity
        for i in range(5, 0, -1):
            val = cleaned.get(f"exclusive_bf_check_{i}")
            if val:
                last = val
                break
            count-=1
            
        cleaned["exclusive_bf_check_last"] = last
        return cleaned

    # -------------------- helpers: UI & data --------------------

    def _apply_max_date_on_widgets(self, today_str: str):
        """Set max=TODAY on all visit date inputs (client-side UX)."""
        for i in range(1, 6):
            fld = f"exclusive_bf_check_{i}"
            if fld in self.fields:
                self.fields[fld].widget.attrs["max"] = today_str

    def _guard_no_future_dates(self, cleaned):
        """Server-side guard: prevent dates beyond PH 'today'."""
        for i in range(1, 6):
            fld = f"exclusive_bf_check_{i}"
            val = cleaned.get(fld)
            if isinstance(val, date) and val > self._today_ph:
                self.add_error(fld, "Date cannot be in the future.")

    def _fetch_child_bf_details(self):
        """
        Call the repository once to get combined rows
        (checks in any order + latest feeding type attached).
        """
        if not self._repo or self._child_health_record_id is None:
            return []
        return self._repo.fetch_child_details_bf_display_by_chr_id(self._child_health_record_id) or []

    def _setup_type_of_feeding_choices(self):
        """Populate select options."""
        choices = [('', 'Select Feeding Type')]

        if self.child_details and isinstance(self.child_details, list):
            if self.child_details[0].get('feeding_type_id') is not None and self.child_details[0].get('feeding_type_name') is not None:
                self.fields['type_of_feeding'].choices = [(self.child_details[0].get('feeding_type_id'), self.child_details[0].get('feeding_type_name'))]
                self.fields['type_of_feeding'].initial = self.child_details[0].get('feeding_type_id')
                return

        if self._repo:
            for ft in (self._repo.fetch_all_feeding_type_dict() or []):
                choices.append((ft['feeding_type_id'], ft['feeding_type_name']))
        self.fields['type_of_feeding'].choices = choices

    def _ordered_checks_oldest_first(self, rows):
        """
        Sort by (check_date ASC, visit_id ASC, bbf_check_id ASC).
        Only rows with a valid check_date are considered.
        """
        if not rows:
            return []
        dated = [r for r in rows if r.get('check_date') is not None]
        return sorted(
            dated,
            key=lambda r: (
                r.get('check_date'),
                r.get('visit_id') or 0,
                r.get('bbf_check_id') or 0,
            ),
        )

    def _populate_bf_checks_from_details(self, rows):
        """Map oldest → exclusive_bf_check_1 … newest → _5."""
        ordered = self._ordered_checks_oldest_first(rows)
        for idx, rec in enumerate(ordered[:5], start=1):
            fld = f"exclusive_bf_check_{idx}"
            if fld in self.fields:
                self.fields[fld].initial = rec.get('check_date')

    def _populate_type_of_feeding_from_details(self, rows):
        """Set the select initial value from the latest visit's feeding type."""
        if not rows:
            return
        # If SQL attaches 'latest' on each row, any row with ft id will do; pick the latest among them.
        candidates = [r for r in rows if r.get('feeding_type_id') is not None]

        def latest_key(r):
            return (
                r.get('check_date') or None,
                r.get('visit_id') or -1,
                r.get('bbf_check_id') or -1,
            )

        if candidates:
            latest = max(candidates, key=latest_key)
            ft_id = latest.get('feeding_type_id')
            ft_name = latest.get('feeding_type_name')
            if ft_id is not None and ft_name is not None:
                self.fields['type_of_feeding'].initial = (ft_id, ft_name)
                self.fields['type_of_feeding'].widget.attrs['readonly'] = True

    def _apply_succession_lock(self):
        """Disable visit i if visit i-1 is empty (UX convenience)."""
        for i in range(2, 6):
            prev = f"exclusive_bf_check_{i-1}"
            curr = f"exclusive_bf_check_{i}"
            if not self.fields.get(prev) or not self.fields[prev].initial:
                if curr in self.fields:
                    self.fields[curr].widget.attrs['disabled'] = 'disabled'
            else:
                if curr in self.fields:
                    self.fields[curr].widget.attrs.pop('disabled', None)
