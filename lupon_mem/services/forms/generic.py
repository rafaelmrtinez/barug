from .. import form_shared as FS

class GenericAcroHandler:
    """Answers-only mapping; no defaults; works for any AcroForm."""
    def build_name_value_map(self, form_id: int, submission_id: int) -> dict:
        return FS.answers_to_names_strict(form_id, submission_id)
