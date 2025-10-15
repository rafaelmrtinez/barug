from typing import Protocol

class FormHandler(Protocol):
    """
    Contract for per-form handlers.

    Implement:
      build_name_value_map(form_id: int, submission_id: int) -> dict
        Return a dict of {acro_field_name: value} for AcroForm PDFs.
        If your target PDF is not an AcroForm, return {} and let the renderer
        fall back to placements.
    """
    def build_name_value_map(self, form_id: int, submission_id: int) -> dict: ...
