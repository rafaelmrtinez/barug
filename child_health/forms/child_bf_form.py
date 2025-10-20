from django import forms
from datetime import datetime, date

from barug.utility.custom_date_time_util import DateAndTimeUtility
from child_health.repository import ChildHealthRecordRepository
from maternal.forms.maternal_identification_form import add_bootstrap_classes


class ChildBreastFeedingForm(forms.Form):
    """Form for tracking exclusive breastfeeding checks and feeding type."""

    type_of_feeding = forms.ChoiceField(
        label="Type of Feeding",
        required=True,
        choices=[],
        error_messages={'required': 'Please select a type of feeding.'},
    )

    # Create fields for 5 visits dynamically
    for i in range(1, 6):
        locals()[f"exclusive_bf_check_{i}"] = forms.DateField(
            label=f"Exclusive BF check (Visit {i})",
            required=False,
            widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            error_messages={
                'required': f'Please provide the date for Visit {i}.'
            },
        )
    del i

    form_type = forms.CharField(initial="bf_feeding_form", widget=forms.HiddenInput())

    # -------------------- INIT --------------------

    def __init__(self, *args, chr_repo: ChildHealthRecordRepository | None = None,
                 child_health_record_id: int | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)

        self._repo = chr_repo
        self._child_health_record_id = child_health_record_id
        self._today_str = DateAndTimeUtility.get_current_date()
        self._today = datetime.strptime(self._today_str, "%Y-%m-%d").date()

        self._apply_max_date_to_fields(self._today_str)
        self.child_details = self._fetch_child_bf_details()
        self._configure_feeding_choices()
        self._populate_bf_checks()
        self._apply_succession_lock()
        self._lock_existing_visits()

    # -------------------- VALIDATION --------------------

    def clean(self):
        cleaned = super().clean()
        self._validate_no_future_dates(cleaned)
        self._validate_visit_sequence(cleaned)
        cleaned["exclusive_bf_check_last"] = self._get_latest_visit_date(cleaned)
        return cleaned

    # -------------------- HELPER METHODS --------------------

    # ----- Setup -----
    def _apply_max_date_to_fields(self, today_str: str):
        """Set max date on all visit date inputs."""
        for i in range(1, 6):
            self.fields[f"exclusive_bf_check_{i}"].widget.attrs["max"] = today_str

    def _fetch_child_bf_details(self):
        """Fetch breastfeeding details from the repository."""
        if not self._repo or not self._child_health_record_id:
            return []
        return self._repo.fetch_child_details_bf_display_by_chr_id(self._child_health_record_id) or []

    def _configure_feeding_choices(self):
        """Setup feeding type choices and initial selection."""
        choices = [('', 'Select Feeding Type')]

        if self.child_details and isinstance(self.child_details, list):
            ft_id = self.child_details[0].get('feeding_type_id')
            ft_name = self.child_details[0].get('feeding_type_name')
            if ft_id and ft_name:
                self.fields['type_of_feeding'].choices = [(ft_id, ft_name)]
                self.fields['type_of_feeding'].initial = ft_id
                return

        if self._repo:
            for ft in self._repo.fetch_all_feeding_type() or []:
                choices.append((ft['feeding_type_id'], ft['feeding_type_name']))
        self.fields['type_of_feeding'].choices = choices

    # ----- Population -----
    def _populate_bf_checks(self):
        """Populate visit fields from existing data."""
        for idx, rec in enumerate(self._get_ordered_checks()[:5], start=1):
            self.fields[f"exclusive_bf_check_{idx}"].initial = rec.get('check_date')

    def _get_ordered_checks(self):
        """Return breastfeeding checks ordered by oldest first."""
        if not self.child_details:
            return []
        dated = [r for r in self.child_details if r.get('check_date')]
        return sorted(dated, key=lambda r: (
            r.get('check_date'),
            r.get('visit_id') or 0,
            r.get('bbf_check_id') or 0,
        ))

    def _apply_succession_lock(self):
        """Disable visit fields that should follow unfilled visits."""
        for i in range(2, 6):
            prev = self.fields[f"exclusive_bf_check_{i-1}"]
            curr = self.fields[f"exclusive_bf_check_{i}"]
            if not prev.initial:
                curr.widget.attrs['disabled'] = 'disabled'
            else:
                curr.widget.attrs.pop('disabled', None)

    def _lock_existing_visits(self):
        """Make already-filled visits read-only."""
        for i in range(1, 6):
            if self.fields[f"exclusive_bf_check_{i}"].initial:
                self.fields[f"exclusive_bf_check_{i}"].widget.attrs['readonly'] = True

    # ----- Validation -----
    def _validate_no_future_dates(self, cleaned):
        """Reject dates beyond today's date."""
        for i in range(1, 6):
            val = cleaned.get(f"exclusive_bf_check_{i}")
            if isinstance(val, date) and val > self._today:
                self.add_error(f"exclusive_bf_check_{i}", "Date cannot be in the future.")

    def _validate_visit_sequence(self, cleaned):
        """Ensure visits are filled in order."""
        for i in range(2, 6):
            if cleaned.get(f"exclusive_bf_check_{i}") and not cleaned.get(f"exclusive_bf_check_{i-1}"):
                self.add_error(
                    f"exclusive_bf_check_{i}",
                    f"Please fill Visit {i-1} first."
                )

    def _get_latest_visit_date(self, cleaned):
        """Return the most recent filled visit date."""
        for i in range(5, 0, -1):
            if cleaned.get(f"exclusive_bf_check_{i}"):
                return cleaned[f"exclusive_bf_check_{i}"]
        return None
