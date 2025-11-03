from .. import form_shared as FS

class GenericAcroHandler:
    """Answers-only mapping; no defaults; works for any AcroForm."""
    def build_name_value_map(self, form_id: int, submission_id: int) -> dict:
        return FS.answers_to_names_strict(form_id, submission_id)
    
    def persist_computed(self, *, form_id: int, submission_id: int, case_id: int, out_map: dict) -> None:
        """Default: no persistence of computed values. Specific forms override."""
        return