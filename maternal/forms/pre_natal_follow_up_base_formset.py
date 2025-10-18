from typing import Optional

from django.forms import BaseFormSet, formset_factory
from maternal.forms.pre_natal_follow_up_form import PrenatalFollowUpEntryForm
from maternal.repository import MaternalHealthRecordRepository


class PrenatalFollowUpBaseFormSet(BaseFormSet):
    """
    Optional: forwards kwargs to each child form.
    Add DB-driven `initial` mapping here later if needed.
    """
    def __init__(
        self,
        *args,
        mhr_repository: Optional[MaternalHealthRecordRepository] = None,
        maternal_id: Optional[int] = None,
        role: Optional[str] = None,
        **kwargs
    ):
        # stash custom args to forward in _construct_form
        self._role = role
        self._mhr_repository = mhr_repository
        self._maternal_id = maternal_id

        # If you want to auto-populate initial from repo, you could do it here:
        # if "initial" not in kwargs and mhr_repository and maternal_id:
        #     rows: Iterable[Mapping[str, Any]] = mhr_repository.fetch_prenatal_followups_by_maternal_id(maternal_id) or []
        #     kwargs["initial"] = [{
        #         "date":     r.get("visit_date"),
        #         "aog":      r.get("aog"),
        #         "wt_kg":    r.get("weight_kg"),
        #         "bp":       r.get("bp"),
        #         "findings": r.get("findings"),
        #         "notes":    r.get("notes"),
        #     } for r in rows]

        super().__init__(*args, **kwargs)

    def _construct_form(self, i, **kwargs):
        # forward to each child form so it can apply role-based disabling
        kwargs.setdefault("role", self._role)
        kwargs.setdefault("mhr_repository", self._mhr_repository)
        kwargs.setdefault("maternal_id", self._maternal_id)
        return super()._construct_form(i, **kwargs)


PrenatalFollowUpFormSet = formset_factory(
    PrenatalFollowUpEntryForm,
    formset=PrenatalFollowUpBaseFormSet,  # you can omit if you don’t need it
    extra=0,
    can_delete=True,
)