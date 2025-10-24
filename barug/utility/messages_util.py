from django.contrib import messages
from django.core.exceptions import NON_FIELD_ERRORS

from django.forms.formsets import BaseFormSet

class MessageUtility:
    
    @staticmethod
    def push_form_errors_as_messages(request, form, level=messages.WARNING):
        """Push form or formset validation errors into Django messages.

        Supports both Form and FormSet objects.

        - For a Form: uses non_field_errors() and errors.get_json_data().
        - For a FormSet: uses non_form_errors() and iterates per-form errors.
        """
        # non-field / non-form errors
        if hasattr(form, "non_field_errors"):
            # regular Form
            for msg in form.non_field_errors():
                messages.add_message(request, level, msg)
        elif hasattr(form, "non_form_errors"):
            # FormSet
            for msg in form.non_form_errors():
                messages.add_message(request, level, msg)

        # field-level errors
        errs = getattr(form, "errors", None)
        if errs is None:
            return

        # Form.errors usually supports get_json_data()
        if hasattr(errs, "get_json_data"):
            data = errs.get_json_data()
            for field, field_errs in data.items():
                if field == NON_FIELD_ERRORS:
                    continue
                for e in field_errs:
                    messages.add_message(request, level, e.get("message") or str(e))
            return

        # FormSet.errors is a list of ErrorDicts (one per form). Iterate them
        if isinstance(errs, (list, tuple)):
            for form_errors in errs:
                # form_errors is an ErrorDict mapping field->ErrorList
                for field, field_errs in getattr(form_errors, "items", lambda: [])():
                    for e in field_errs:
                        # e may be a ValidationError or string; convert to string
                        messages.add_message(request, level, str(e))
            return

        # Fallback: try to iterate like a mapping
        try:
            for field, field_errs in errs.items():
                if field == NON_FIELD_ERRORS:
                    continue
                for e in field_errs:
                    messages.add_message(request, level, str(e))
        except Exception:
            # give up quietly if the structure is unexpected
            return