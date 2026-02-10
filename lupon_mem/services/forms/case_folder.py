# lupon_mem/services/forms/case_folder.py
from __future__ import annotations
from django.db import connection
from .. import form_shared as FS
from ..case_forms_utils import fetch_all_case_forms_data

class CaseFolderHandler:
    def build_name_value_map(self, form_id:int, submission_id:int, case_id:int=None)->dict:
        print(f"[CaseFolderHandler] START form_id={form_id} submission_id={submission_id} case_id={case_id}")
        answers = {}
        if submission_id:
            answers = FS.load_answers(submission_id)
        
        if not case_id and submission_id:
            with connection.cursor() as cur:
                cur.execute("SELECT blotter_case_id FROM blotter_kp_submission WHERE submission_id=%s", [submission_id])
                row = cur.fetchone()
                case_id = row[0] if row else None
        
        print(f"[CaseFolderHandler] case_id={case_id}")
        if case_id:
            data = fetch_all_case_forms_data(case_id)
            kp8 = data["kp8"]
            kp9 = data["kp9"]
            kp9p2 = data["kp9p2"]
            kp16 = data["kp16"]
            
            print(f"[CaseFolderHandler] Prefilling answers...")
            if len(kp8) >= 1:
                dt = f"{kp8[0]['hearing_date']} {kp8[0]['hearing_time']}".strip()
                answers.setdefault('210', dt)
                answers.setdefault('217', dt)
            if len(kp8) >= 2:
                dt = f"{kp8[1]['hearing_date']} {kp8[1]['hearing_time']}".strip()
                answers.setdefault('43', dt)
                answers.setdefault('131', dt)
            if len(kp8) >= 3:
                dt = f"{kp8[2]['hearing_date']} {kp8[2]['hearing_time']}".strip()
                answers.setdefault('254', dt)
                answers.setdefault('88', dt)
            
            if len(kp9) >= 1: answers.setdefault('266', kp9[0])
            if len(kp9) >= 2: answers.setdefault('286', kp9[1])
            if len(kp9) >= 3: answers.setdefault('106', kp9[2])
            
            if len(kp9p2) >= 1: answers.setdefault('34', kp9p2[0])
            if len(kp9p2) >= 2: answers.setdefault('159', kp9p2[1])
            if len(kp9p2) >= 3: answers.setdefault('740', kp9p2[2])
            
            if kp16: answers.setdefault('185', kp16)
        
        print(f"[CaseFolderHandler] END answers={answers}")
        return answers
