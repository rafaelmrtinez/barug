from typing import Optional

from django.forms import BaseFormSet


class PrenatalFollowUpBaseFormSet(BaseFormSet):
    """
    Loads initial rows from the repository if `initial` is not supplied.

    Expects repository method:
        mhr_repository.fetch_prenatal_followups_by_maternal_id(maternal_id) -> Iterable[Mapping[str, Any]]

    Each row should include keys:
        visit_date, aog, weight_kg, bp, leopolds_findings, notes
    """
    def __init__(self, *args, mhr_repository=None, maternal_id: Optional[int] = None, **kwargs):
        super().__init__(*args, **kwargs)
