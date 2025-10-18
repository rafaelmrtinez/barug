# maternal/forms/widgets.py
from django.forms.widgets import ClearableFileInput

class MultiImageInput(ClearableFileInput):
    # This is the key: allow multiple files to be selected
    allow_multiple_selected = True
