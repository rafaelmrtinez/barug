# notifications/kp.py
from __future__ import annotations
from .service import NotifierService, NotifyTarget, PERSON, STAFF
from . import repo

def _notify_parties_generic(svc: NotifierService, *, kp_label: str, case_id: int, case_num: str, title: str, body_tpl: str):
    # residents
    for role, person_id in repo.case_party_person_ids(case_id):
        body = body_tpl.format(case_num=case_num, role=role)
        svc.notify_user(
            target=NotifyTarget(user_type_id=PERSON, person_id=person_id),
            title=f"{title} — Case {case_num}",
            body=body,
            deep_link=f"/resident/cases/{case_id}",
        )
    # lupon staff
    for (staff_id,) in repo.lupon_staff_ids():
        svc.notify_user(
            target=NotifyTarget(user_type_id=STAFF, staff_id=staff_id),
            title=f"New {kp_label} Submission",
            body=f"{kp_label} form has been submitted for Case #{case_num}",
            deep_link=f"/lupon_mem/case/{case_id}/",
        )

# Specifics mirroring your previous functions
def kp7_complaint_filed(svc: NotifierService, *, case_id: int, case_num: str):
    for role, person_id in repo.case_party_person_ids(case_id):
        if role == 'complainant':
            svc.notify_user(
                target=NotifyTarget(user_type_id=PERSON, person_id=person_id),
                title="Complaint Filed",
                body=f"Your complaint has been filed as Case #{case_num}",
                deep_link=f"/resident/cases/{case_id}",
            )
        else:
            svc.notify_user(
                target=NotifyTarget(user_type_id=PERSON, person_id=person_id),
                title="New Case Filed Against You",
                body=f"A complaint has been filed against you — Case #{case_num}",
                deep_link=f"/resident/cases/{case_id}",
            )

def kp8_hearing_scheduled(svc: NotifierService, *, case_id: int, case_num: str, hearing_date: str, hearing_time: str):
    for (person_id,) in repo._exec("SELECT person_id FROM complainant_case WHERE blotter_case_id=%s", (case_id,)):
        svc.notify_user(
            target=NotifyTarget(user_type_id=PERSON, person_id=person_id),
            title=f"Hearing Scheduled — Case {case_num}",
            body=f"Hearing scheduled for {hearing_date} at {hearing_time}",
            deep_link=f"/resident/cases/{case_id}",
        )
    for (staff_id,) in repo.lupon_staff_ids():
        svc.notify_user(
            target=NotifyTarget(user_type_id=STAFF, staff_id=staff_id),
            title="New KP-8 Submission",
            body=f"NOTICE OF HEARING has been submitted for Case #{case_num}",
            deep_link=f"/lupon_mem/case/{case_id}/",
        )

def kp9_summon_issued(svc: NotifierService, *, case_id: int, case_num: str, hearing_date: str, hearing_time: str):
    for (person_id,) in repo._exec("SELECT person_id FROM respondent_case WHERE blotter_case_id=%s", (case_id,)):
        svc.notify_user(
            target=NotifyTarget(user_type_id=PERSON, person_id=person_id),
            title=f"Notice of Hearing — Case {case_num}",
            body=f"You are required to appear {hearing_date} at {hearing_time} for your mediation hearing. (Case {case_num})",
            deep_link=f"/resident/cases/{case_id}",
        )

# Generic wrappers (10–26 + extras)
def kp10_pangkat_constituted(svc: NotifierService, *, case_id: int, case_num: str):
    _notify_parties_generic(svc, kp_label="KP-10", case_id=case_id, case_num=case_num,
                            title="Pangkat Constitution",
                            body_tpl="Pangkat has been constituted for Case #{case_num}")

def kp11_mediation_proceedings(svc: NotifierService, *, case_id: int, case_num: str):
    _notify_parties_generic(svc, kp_label="KP-11", case_id=case_id, case_num=case_num,
                            title="Mediation Proceedings",
                            body_tpl="Mediation proceedings have started for Case #{case_num}")

def kp12_conciliation_notice(svc: NotifierService, *, case_id: int, case_num: str):
    _notify_parties_generic(svc, kp_label="KP-12", case_id=case_id, case_num=case_num,
                            title="Notice of Hearing (Conciliation)",
                            body_tpl="Notice of hearing for conciliation has been issued for Case #{case_num}")

# … continue your KP-13..KP-26 and extras the same way …
