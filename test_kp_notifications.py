#!/usr/bin/env python3
"""
Test script to show all KP notification messages
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'barug.settings')
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
django.setup()

from notifications.service import NotifierService, NotifyTarget, PERSON, STAFF
from notifications import kp as kp_notify

class MockNotifierService:
    def __init__(self):
        self.notifications = []
    
    def notify_user(self, target, title, body, deep_link):
        user_type = "PERSON" if target.user_type_id == PERSON else "STAFF"
        user_id = target.person_id if target.person_id else target.staff_id
        
        self.notifications.append({
            'user_type': user_type,
            'user_id': user_id,
            'title': title,
            'body': body,
            'deep_link': deep_link
        })
        
        print(f"[{user_type}] User ID: {user_id}")
        print(f"   Title: {title}")
        print(f"   Body: {body}")
        print(f"   Link: {deep_link}")
        print()

# Mock repo functions
class MockRepo:
    @staticmethod
    def case_party_person_ids(case_id):
        return [
            ('complainant', 101),
            ('respondent', 102)
        ]
    
    @staticmethod
    def lupon_staff_ids():
        return [(201,), (202,)]
    
    @staticmethod
    def _exec(query, params):
        if "complainant_case" in query:
            return [(101,)]
        elif "respondent_case" in query:
            return [(102,)]
        return []

# Patch the repo module
import notifications.repo as repo
repo.case_party_person_ids = MockRepo.case_party_person_ids
repo.lupon_staff_ids = MockRepo.lupon_staff_ids
repo._exec = MockRepo._exec

def test_all_kp_notifications():
    print("=" * 80)
    print("TESTING ALL KP FORM NOTIFICATIONS")
    print("=" * 80)
    print()
    
    mock_svc = MockNotifierService()
    case_id = 12345
    case_num = "2024-001"
    
    kp_functions = [
        ("KP-7", kp_notify.kp7_complaint_filed),
        ("KP-8", lambda svc, **kwargs: kp_notify.kp8_hearing_scheduled(svc, hearing_date="December 15, 2024", hearing_time="2:00 PM", **kwargs)),
        ("KP-9", lambda svc, **kwargs: kp_notify.kp9_summon_issued(svc, hearing_date="December 15, 2024", hearing_time="2:00 PM", **kwargs)),
        ("KP-10", kp_notify.kp10_pangkat_constituted),
        ("KP-11", kp_notify.kp11_mediation_proceedings),
        ("KP-12", kp_notify.kp12_conciliation_notice),
        ("KP-13", kp_notify.kp13_subpoena_letter),
        ("KP-14", kp_notify.kp14_agreement_arbitration),
        ("KP-15", kp_notify.kp15_arbitration_award),
        ("KP-16", kp_notify.kp16_amicable_settlement),
        ("KP-17", kp_notify.kp17_repudiation),
        ("KP-18", kp_notify.kp18_hearing_complainant),
        ("KP-19", kp_notify.kp19_hearing_respondent),
        ("KP-20", kp_notify.kp20_certification_file_action),
        ("KP-21", kp_notify.kp21_certification_bar_action),
        ("KP-22", kp_notify.kp22_certification_bar_action_respondent),
        ("KP-23", kp_notify.kp23_execution_settlement),
        ("KP-24", kp_notify.kp24_motion_execution),
        ("KP-25", kp_notify.kp25_satisfaction_judgment),
    ]
    
    for kp_name, kp_func in kp_functions:
        print(f"[{kp_name}] NOTIFICATIONS")
        print("-" * 50)
        
        try:
            kp_func(mock_svc, case_id=case_id, case_num=case_num)
        except Exception as e:
            print(f"ERROR testing {kp_name}: {e}")
        
        print()

if __name__ == "__main__":
    test_all_kp_notifications()