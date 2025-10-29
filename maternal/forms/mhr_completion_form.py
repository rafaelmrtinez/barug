from django import forms

from maternal.forms.maternal_identification_form import add_bootstrap_classes
from maternal.repository import MaternalHealthRecordRepository

class MHRCompletionForm(forms.Form):
    # Turn confirmation into a dropdown of target statuses (include ONGOING)
    confirm_complete = forms.TypedChoiceField(
        required=True,
        label="Change maternal health record status to",
        coerce=int,
        choices=(),
        error_messages={
            'required': 'You must select a status to set for the maternal health record.'
        }
    )
    form_type = forms.CharField(
        initial="mhr_completion_form",
        widget=forms.HiddenInput(attrs={'id': 'mhr_completion_form'})
    )

    def __init__(self, repository: MaternalHealthRecordRepository, mhr_id: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
        self._repository = repository
        
        self._existing_data = self._repository.fetch_maternal_health_record_status_by_mhr_id(maternal_record_id=mhr_id)
        # normalize existing status id (int) if present
        existing_status_id = None
        if isinstance(self._existing_data, dict):
            try:
                existing_status_id = int(self._existing_data.get('record_status_id')) if self._existing_data.get('record_status_id') is not None else None
            except (TypeError, ValueError):
                existing_status_id = None
        # also extract existing status name (if available)
        existing_status_name = None
        if isinstance(self._existing_data, dict):
            existing_status_name = (self._existing_data.get('record_status_name') or '').strip() or None
        elif isinstance(self._existing_data, (list, tuple)):
            # assume (id, name)
            try:
                existing_status_name = (self._existing_data[1] or '').strip() or None
            except Exception:
                existing_status_name = None

        # Fetch all statuses and convert to (id, name) tuples — include ONGOING
        rows = self._repository.fetch_all_mhr_completion_status() or []
        choices = []
        for r in rows:
            # support both dict rows and tuple/list rows returned by different ctx helpers
            rs_id = None
            rs_name = None
            if isinstance(r, dict):
                rs_id_raw = r.get('record_status_id') if 'record_status_id' in r else r.get('record_status') if 'record_status' in r else None
                rs_name_raw = r.get('record_status_name') or r.get('record_status_name') or r.get('status_name')
                rs_id = None if rs_id_raw is None else rs_id_raw
                rs_name = (rs_name_raw or '').strip()
            elif isinstance(r, (list, tuple)):
                # assume (id, name)
                try:
                    rs_id = r[0]
                    rs_name = (r[1] or '').strip()
                except Exception:
                    continue
            else:
                # unexpected shape; skip
                continue

            try:
                rs_id = int(rs_id)
            except (TypeError, ValueError):
                # skip malformed ids
                continue

            # include all statuses (including ONGOING)
            choices.append((rs_id, rs_name))

        # Assign choices to the field (TypedChoiceField will coerce selected value to int)
        self.fields['confirm_complete'].choices = choices

        # expose the current status name and whether status change should be allowed
        allow_status_change = False
        if existing_status_name and isinstance(existing_status_name, str):
            if existing_status_name.upper() in ('COMPLETE', 'INCOMPLETE', 'ONGOING'):
                allow_status_change = True

        # set widget data attributes so templates/JS can decide what to disable
        widget_attrs = self.fields['confirm_complete'].widget.attrs or {}
        if existing_status_name:
            widget_attrs['data-current-status-name'] = existing_status_name
        widget_attrs['data-allow-status-change'] = '1' if allow_status_change else '0'
        self.fields['confirm_complete'].widget.attrs = widget_attrs

        # Set initial selection to the existing status id so the dropdown shows current state
        if existing_status_id is not None:
            try:
                self.initial['confirm_complete'] = int(existing_status_id)
                # also set field initial so widget renders pre-selected
                self.fields['confirm_complete'].initial = int(existing_status_id)
            except (TypeError, ValueError):
                pass