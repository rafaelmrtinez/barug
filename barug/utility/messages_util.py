from django.contrib import messages
from django.core.exceptions import NON_FIELD_ERRORS

class MessageUtility:
    
    @staticmethod
    def push_form_errors_as_messages(request, form, level=messages.WARNING):
        for msg in form.non_field_errors():
            messages.add_message(request, level, msg)

        data = form.errors.get_json_data()
        for field, errs in data.items():
            if field == NON_FIELD_ERRORS:
                continue
            for e in errs:
                messages.add_message(request, level, e["message"])