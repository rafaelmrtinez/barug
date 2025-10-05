from django.test import TestCase
from dataclasses import asdict

from src.app.transfer_objects.request.breast_feeding_type_request import BreastFeedingCheckRequest
from src.app.transfer_objects.request.child_immunization_request import ChildImmunizationRequest
from src.app.transfer_objects.request.child_iron_supplement_request import ChildIronSupplementRequest
from src.app.transfer_objects.request.child_monitoring_request import ChildMonitoringRequest
from src.app.transfer_objects.request.child_screening_request import ChildScreeningRequest
from src.app.transfer_objects.request.child_visit_request import ChildVisitRequest
from src.app.transfer_objects.request.child_vitamins_request import ChildVitaminsRequest

import json


class TestChildVisitRequest(TestCase):
    
    def setUp(self):
        self.vitamins = ChildVitaminsRequest(
            dose_no=1,
            date_given="2023-10-01"
        )
        self.iron_supplements = ChildIronSupplementRequest(
            date_started="2023-10-01",
            date_completed=""
        )
        self.screenings = ChildScreeningRequest(
            is_protected_at_birth=True,
            date_assessed="2023-10-01",
            anemic_seen=False,
            anemic_given_iron=False,
            birth_weight=3.2,
            is_low_birth_weight=False,
            iron_seen_2_6_mos=False,
            iron_given_2_6_mos=False
        )
        self.monitoring_logs = [
            ChildMonitoringRequest(
                check_date="2023-10-01",
                age=12,
                weight=9.5,
                temperature=36.5,
                height=75.0,
                findings="Healthy",
                notes="No issues"    
            ),
            ChildMonitoringRequest(
                check_date="2023-10-01",
                age=12,
                weight=9.5,
                temperature=36.5,
                height=75.0,
                findings="Healthy",
                notes="No issues"    
            ),
        ]
        self.bf_checks = [
            BreastFeedingCheckRequest(check_date="2023-10-01"),
            BreastFeedingCheckRequest(check_date="2023-10-02")
        ]
        self.child_immunizations = [
            ChildImmunizationRequest(immunization_type_id=1, date_given="2023-10-01", immunization_stage_given_id=1),
            ChildImmunizationRequest(immunization_type_id=2, date_given="2023-10-02", immunization_stage_given_id=2)
        ]
        self.child_visit_request = ChildVisitRequest(
            p_child_record_id=1,
            p_assessed_by_id=0,
            p_visit_date="2023-10-01",
            p_feeding_type_id=1,
            p_referred_nbs_date="2023-10-05",
            p_child_immunizations=self.child_immunizations,
            p_bf_checks=self.bf_checks,
            p_monitoring_logs=self.monitoring_logs,
            p_screenings=self.screenings,
            p_iron_supplements=self.iron_supplements,
            p_vitamin_a=[self.vitamins, self.vitamins]
        )
        
    def test_child_visit_obj_to_json(self):
        json_output = json.dumps(asdict(self.child_visit_request), indent=4, ensure_ascii=False)
        print(f"ChildVisitRequest JSON: {json_output}\n")

        
    def test_child_visit_request_creation(self):
        print(f"ChildVisitRequest: {self.child_visit_request}")
        
        self.assertIsNotNone(self.child_visit_request)
        self.assertIsNotNone(self.child_visit_request.p_child_immunizations)
        self.assertIsNotNone(self.child_visit_request.p_bf_checks)
        self.assertIsNotNone(self.child_visit_request.p_monitoring_logs)
        self.assertIsNotNone(self.child_visit_request.p_screenings)
        self.assertIsNotNone(self.child_visit_request.p_iron_supplements)
        self.assertIsNotNone(self.child_visit_request.p_vitamin_a)