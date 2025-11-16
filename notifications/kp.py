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
    for role, person_id in repo.case_party_person_ids(case_id):
        svc.notify_user(
            target=NotifyTarget(user_type_id=PERSON, person_id=person_id),
            title="Pangkat Members Selected",
            body=f"The Pangkat ng Tagapagkasundo has been formed to mediate your case #{case_num}. You will be notified of the hearing schedule.",
            deep_link=f"/resident/cases/{case_id}",
        )
    for (staff_id,) in repo.lupon_staff_ids():
        svc.notify_user(
            target=NotifyTarget(user_type_id=STAFF, staff_id=staff_id),
            title="Pangkat Constitution Complete",
            body=f"Pangkat members have been selected for mediation in Case #{case_num}",
            deep_link=f"/lupon_mem/case/{case_id}/",
        )

def kp11_mediation_proceedings(svc: NotifierService, *, case_id: int, case_num: str):
    for role, person_id in repo.case_party_person_ids(case_id):
        svc.notify_user(
            target=NotifyTarget(user_type_id=PERSON, person_id=person_id),
            title="Pangkat Member Notification",
            body=f"A Pangkat member has been notified to participate in the mediation of Case #{case_num}",
            deep_link=f"/resident/cases/{case_id}",
        )
    for (staff_id,) in repo.lupon_staff_ids():
        svc.notify_user(
            target=NotifyTarget(user_type_id=STAFF, staff_id=staff_id),
            title="Pangkat Member Notified",
            body=f"Notice sent to chosen Pangkat member for Case #{case_num}",
            deep_link=f"/lupon_mem/case/{case_id}/",
        )

def kp12_conciliation_notice(svc: NotifierService, *, case_id: int, case_num: str):
    for role, person_id in repo.case_party_person_ids(case_id):
        svc.notify_user(
            target=NotifyTarget(user_type_id=PERSON, person_id=person_id),
            title="Conciliation Hearing Scheduled",
            body=f"You are required to attend the conciliation hearing for Case #{case_num}. Check the notice for date and time.",
            deep_link=f"/resident/cases/{case_id}",
        )
    for (staff_id,) in repo.lupon_staff_ids():
        svc.notify_user(
            target=NotifyTarget(user_type_id=STAFF, staff_id=staff_id),
            title="Conciliation Hearing Notice Issued",
            body=f"Notice of hearing for conciliation proceedings sent for Case #{case_num}",
            deep_link=f"/lupon_mem/case/{case_id}/",
        )

def kp13_subpoena_letter(svc: NotifierService, *, case_id: int, case_num: str):
    for role, person_id in repo.case_party_person_ids(case_id):
        svc.notify_user(
            target=NotifyTarget(user_type_id=PERSON, person_id=person_id),
            title="Subpoena Issued",
            body=f"A subpoena has been issued requiring your appearance or witness testimony for Case #{case_num}",
            deep_link=f"/resident/cases/{case_id}",
        )
    for (staff_id,) in repo.lupon_staff_ids():
        svc.notify_user(
            target=NotifyTarget(user_type_id=STAFF, staff_id=staff_id),
            title="Subpoena Letter Issued",
            body=f"Subpoena letter has been issued for witness/party in Case #{case_num}",
            deep_link=f"/lupon_mem/case/{case_id}/",
        )

def kp14_agreement_arbitration(svc: NotifierService, *, case_id: int, case_num: str):
    for role, person_id in repo.case_party_person_ids(case_id):
        svc.notify_user(
            target=NotifyTarget(user_type_id=PERSON, person_id=person_id),
            title="Arbitration Agreement Signed",
            body=f"Both parties have agreed to arbitration for Case #{case_num}. An arbitrator will decide the outcome.",
            deep_link=f"/resident/cases/{case_id}",
        )
    for (staff_id,) in repo.lupon_staff_ids():
        svc.notify_user(
            target=NotifyTarget(user_type_id=STAFF, staff_id=staff_id),
            title="Arbitration Agreement Filed",
            body=f"Parties have agreed to arbitration proceedings for Case #{case_num}",
            deep_link=f"/lupon_mem/case/{case_id}/",
        )

def kp15_arbitration_award(svc: NotifierService, *, case_id: int, case_num: str):
    for role, person_id in repo.case_party_person_ids(case_id):
        svc.notify_user(
            target=NotifyTarget(user_type_id=PERSON, person_id=person_id),
            title="Arbitration Decision Issued",
            body=f"The arbitrator has made a final decision on Case #{case_num}. Review the award details.",
            deep_link=f"/resident/cases/{case_id}",
        )
    for (staff_id,) in repo.lupon_staff_ids():
        svc.notify_user(
            target=NotifyTarget(user_type_id=STAFF, staff_id=staff_id),
            title="Arbitration Award Completed",
            body=f"Final arbitration award has been issued for Case #{case_num}",
            deep_link=f"/lupon_mem/case/{case_id}/",
        )

def kp16_amicable_settlement(svc: NotifierService, *, case_id: int, case_num: str):
    for role, person_id in repo.case_party_person_ids(case_id):
        svc.notify_user(
            target=NotifyTarget(user_type_id=PERSON, person_id=person_id),
            title="Settlement Agreement Reached",
            body=f"Congratulations! An amicable settlement has been reached for Case #{case_num}. Please comply with the agreed terms.",
            deep_link=f"/resident/cases/{case_id}",
        )
    for (staff_id,) in repo.lupon_staff_ids():
        svc.notify_user(
            target=NotifyTarget(user_type_id=STAFF, staff_id=staff_id),
            title="Amicable Settlement Achieved",
            body=f"Parties have reached an amicable settlement for Case #{case_num}",
            deep_link=f"/lupon_mem/case/{case_id}/",
        )

def kp17_repudiation(svc: NotifierService, *, case_id: int, case_num: str):
    for role, person_id in repo.case_party_person_ids(case_id):
        svc.notify_user(
            target=NotifyTarget(user_type_id=PERSON, person_id=person_id),
            title="Settlement Challenged",
            body=f"A party has filed a repudiation challenging the settlement in Case #{case_num} due to fraud, violence, or intimidation.",
            deep_link=f"/resident/cases/{case_id}",
        )
    for (staff_id,) in repo.lupon_staff_ids():
        svc.notify_user(
            target=NotifyTarget(user_type_id=STAFF, staff_id=staff_id),
            title="Repudiation Filed",
            body=f"Settlement repudiation has been filed for Case #{case_num}",
            deep_link=f"/lupon_mem/case/{case_id}/",
        )

def kp18_hearing_complainant(svc: NotifierService, *, case_id: int, case_num: str):
    for (person_id,) in repo._exec("SELECT person_id FROM complainant_case WHERE blotter_case_id=%s", (case_id,)):
        svc.notify_user(
            target=NotifyTarget(user_type_id=PERSON, person_id=person_id),
            title="Hearing Notice for Complainant",
            body=f"You are required to attend the hearing as complainant for Case #{case_num}. Check the notice for details.",
            deep_link=f"/resident/cases/{case_id}",
        )
    for (staff_id,) in repo.lupon_staff_ids():
        svc.notify_user(
            target=NotifyTarget(user_type_id=STAFF, staff_id=staff_id),
            title="Complainant Hearing Notice Sent",
            body=f"Hearing notice has been sent to complainant for Case #{case_num}",
            deep_link=f"/lupon_mem/case/{case_id}/",
        )

def kp19_hearing_respondent(svc: NotifierService, *, case_id: int, case_num: str):
    for (person_id,) in repo._exec("SELECT person_id FROM respondent_case WHERE blotter_case_id=%s", (case_id,)):
        svc.notify_user(
            target=NotifyTarget(user_type_id=PERSON, person_id=person_id),
            title="Hearing Notice for Respondent",
            body=f"You are required to attend the hearing as respondent for Case #{case_num}. Failure to appear may result in default judgment.",
            deep_link=f"/resident/cases/{case_id}",
        )
    for (staff_id,) in repo.lupon_staff_ids():
        svc.notify_user(
            target=NotifyTarget(user_type_id=STAFF, staff_id=staff_id),
            title="Respondent Hearing Notice Sent",
            body=f"Hearing notice has been sent to respondent for Case #{case_num}",
            deep_link=f"/lupon_mem/case/{case_id}/",
        )

def kp20_certification_file_action(svc: NotifierService, *, case_id: int, case_num: str):
    for role, person_id in repo.case_party_person_ids(case_id):
        if role == 'complainant':
            svc.notify_user(
                target=NotifyTarget(user_type_id=PERSON, person_id=person_id),
                title="Court Action Authorized",
                body=f"You may now file your case in court. Certification to file action has been issued for Case #{case_num}.",
                deep_link=f"/resident/cases/{case_id}",
            )
        else:
            svc.notify_user(
                target=NotifyTarget(user_type_id=PERSON, person_id=person_id),
                title="Case May Proceed to Court",
                body=f"The complainant has been authorized to file Case #{case_num} in court due to failed barangay conciliation.",
                deep_link=f"/resident/cases/{case_id}",
            )
    for (staff_id,) in repo.lupon_staff_ids():
        svc.notify_user(
            target=NotifyTarget(user_type_id=STAFF, staff_id=staff_id),
            title="Certification to File Action Issued",
            body=f"Court filing certification has been issued for Case #{case_num}",
            deep_link=f"/lupon_mem/case/{case_id}/",
        )

def kp21_certification_bar_action(svc: NotifierService, *, case_id: int, case_num: str):
    for role, person_id in repo.case_party_person_ids(case_id):
        svc.notify_user(
            target=NotifyTarget(user_type_id=PERSON, person_id=person_id),
            title="Court Filing Prohibited",
            body=f"Case #{case_num} cannot be filed in court. Barangay conciliation is required first or case is not actionable.",
            deep_link=f"/resident/cases/{case_id}",
        )
    for (staff_id,) in repo.lupon_staff_ids():
        svc.notify_user(
            target=NotifyTarget(user_type_id=STAFF, staff_id=staff_id),
            title="Certification to Bar Action Issued",
            body=f"Court filing prohibition certification issued for Case #{case_num}",
            deep_link=f"/lupon_mem/case/{case_id}/",
        )

def kp22_certification_bar_action_respondent(svc: NotifierService, *, case_id: int, case_num: str):
    for (person_id,) in repo._exec("SELECT person_id FROM respondent_case WHERE blotter_case_id=%s", (case_id,)):
        svc.notify_user(
            target=NotifyTarget(user_type_id=PERSON, person_id=person_id),
            title="Court Filing Blocked",
            body=f"As respondent, you are protected from court filing for Case #{case_num} until barangay conciliation is completed.",
            deep_link=f"/resident/cases/{case_id}",
        )
    for (staff_id,) in repo.lupon_staff_ids():
        svc.notify_user(
            target=NotifyTarget(user_type_id=STAFF, staff_id=staff_id),
            title="Respondent Protection Certification",
            body=f"Certification to bar court action issued protecting respondent in Case #{case_num}",
            deep_link=f"/lupon_mem/case/{case_id}/",
        )

def kp23_execution_settlement(svc: NotifierService, *, case_id: int, case_num: str):
    for role, person_id in repo.case_party_person_ids(case_id):
        svc.notify_user(
            target=NotifyTarget(user_type_id=PERSON, person_id=person_id),
            title="Settlement Enforcement",
            body=f"Execution proceedings have been initiated to enforce the settlement agreement in Case #{case_num}.",
            deep_link=f"/resident/cases/{case_id}",
        )
    for (staff_id,) in repo.lupon_staff_ids():
        svc.notify_user(
            target=NotifyTarget(user_type_id=STAFF, staff_id=staff_id),
            title="Settlement Execution Filed",
            body=f"Execution of settlement agreement initiated for Case #{case_num}",
            deep_link=f"/lupon_mem/case/{case_id}/",
        )

def kp24_motion_execution(svc: NotifierService, *, case_id: int, case_num: str):
    for role, person_id in repo.case_party_person_ids(case_id):
        if role == 'complainant':
            svc.notify_user(
                target=NotifyTarget(user_type_id=PERSON, person_id=person_id),
                title="Execution Motion Filed",
                body=f"Your motion for execution has been filed for Case #{case_num}. The settlement will be enforced.",
                deep_link=f"/resident/cases/{case_id}",
            )
        else:
            svc.notify_user(
                target=NotifyTarget(user_type_id=PERSON, person_id=person_id),
                title="Execution Motion Against You",
                body=f"A motion for execution has been filed against you for Case #{case_num}. You must comply with the settlement terms.",
                deep_link=f"/resident/cases/{case_id}",
            )
    for (staff_id,) in repo.lupon_staff_ids():
        svc.notify_user(
            target=NotifyTarget(user_type_id=STAFF, staff_id=staff_id),
            title="Motion for Execution Filed",
            body=f"Motion for execution of settlement filed for Case #{case_num}",
            deep_link=f"/lupon_mem/case/{case_id}/",
        )

def kp25_satisfaction_judgment(svc: NotifierService, *, case_id: int, case_num: str):
    for role, person_id in repo.case_party_person_ids(case_id):
        svc.notify_user(
            target=NotifyTarget(user_type_id=PERSON, person_id=person_id),
            title="Settlement Completed",
            body=f"Case #{case_num} has been fully satisfied. All settlement obligations have been fulfilled.",
            deep_link=f"/resident/cases/{case_id}",
        )
    for (staff_id,) in repo.lupon_staff_ids():
        svc.notify_user(
            target=NotifyTarget(user_type_id=STAFF, staff_id=staff_id),
            title="Satisfaction of Judgment Filed",
            body=f"Settlement satisfaction confirmed for Case #{case_num} - case closed",
            deep_link=f"/lupon_mem/case/{case_id}/",
        )


