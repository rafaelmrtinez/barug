# lupon_mem/services/forms/med3_settled.py
from __future__ import annotations
from typing import Dict, Set
from datetime import datetime as _dt
from zoneinfo import ZoneInfo
import json, logging
from django.db import connection
from .. import form_shared as FS
from ..case_forms_utils import fetch_all_case_forms_data
logger=logging.getLogger(__name__)

_FIELDS = [
 "case_number","dt_filed","complainant_name","respondent_name","complaint_title","case_nature",
 "first_hearing_dt","second_hearing_dt","third_hearing_dt",
 "first_summ_dt","first_offcret_dt","second_summ_dt","second_offcret_dt","third_summ_dt",
 "first_conf_dt","second_conf_dt","third_conf_dt","settlement_dt","third_offcret_dt",
 "point_of_agreement","exec_dt","to_court_dt","to_dilg_dt","monitoring_date","monitoring_remarks",
 "11d_amicable_settlement","complainant_dt","complainant_remarks","respondent_dt","respondent_remarks",
]
_SOURCES: Dict[str, Set[str]] = {k:{k} for k in _FIELDS}
_SOURCES.update({
 "case_number":{"case_number","case_num","brgy_case_number","brgy_case_num","barangay case no.","barangay_case_no"},
 "complainant_name":{"complainant_name","complainants"},
 "respondent_name":{"respondent_name","respondents"},
 "complaint_title":{"complaint_title","case_title","title"},
})
def _today(fmt="%B %d, %Y"): return _dt.now(ZoneInfo("Asia/Manila")).strftime(fmt)

class Med3SettledHandler:
    def _log(self,out:Dict[str,str]):
        try: print("[MED3-SETTLED] fill map:\n", json.dumps({k:out.get(k,'') for k in _FIELDS}, ensure_ascii=False, indent=2))
        except Exception: pass

    def build_name_value_map(self, form_id:int, submission_id:int, case_id:int=None)->dict:
        answers=FS.load_answers(submission_id)
        
        # Get case_id if not provided
        if not case_id:
            with connection.cursor() as cur:
                cur.execute("SELECT blotter_case_id FROM blotter_kp_submission WHERE submission_id=%s", [submission_id])
                row = cur.fetchone()
                case_id = row[0] if row else None
        
        # Fetch KP forms data for prefilling ONLY if no saved answer exists
        if case_id:
            data = fetch_all_case_forms_data(case_id)
            kp7, kp8, kp9, kp9p2, kp16 = data["kp7"], data["kp8"], data["kp9"], data["kp9p2"], data["kp16"]
            case_number = data["case_number"]
            
            # Only set defaults if not already in answers
            if kp7:
                answers.setdefault('case_number', case_number)
                answers.setdefault('dt_filed', kp7['dt_filed'])
                answers.setdefault('complainant_name', kp7['complainant_name'])
                answers.setdefault('respondent_name', kp7['respondent_name'])
                answers.setdefault('complaint_title', kp7['complaint_title'])
            
            from ..case_forms_utils import format_date, format_time
            if len(kp9) >= 1: answers.setdefault('first_summ_dt', format_date(kp9[0]))
            if len(kp9) >= 2: answers.setdefault('second_summ_dt', format_date(kp9[1]))
            if len(kp9) >= 3: answers.setdefault('third_summ_dt', format_date(kp9[2]))
            
            if len(kp9p2) >= 1: answers.setdefault('first_offcret_dt', format_date(kp9p2[0]))
            if len(kp9p2) >= 2: answers.setdefault('second_offcret_dt', format_date(kp9p2[1]))
            if len(kp9p2) >= 3: answers.setdefault('third_offcret_dt', format_date(kp9p2[2]))
            
            if kp16:
                answers.setdefault('settlement_dt', kp16['settlement_dt'])
                answers.setdefault('point_of_agreement', kp16['settlement_statement'])
            
            # KP-8 data
            if len(kp8) >= 1: 
                answers.setdefault('first_hearing_dt', format_date(kp8[0]['date_notified']))
                answers.setdefault('first_conf_dt', f"{format_date(kp8[0]['hearing_date'])} @{format_time(kp8[0]['hearing_time'])}")
            if len(kp8) >= 2: 
                answers.setdefault('second_hearing_dt', format_date(kp8[1]['date_notified']))
                answers.setdefault('second_conf_dt', f"{format_date(kp8[1]['hearing_date'])} @{format_time(kp8[1]['hearing_time'])}")
            if len(kp8) >= 3: 
                answers.setdefault('third_hearing_dt', format_date(kp8[2]['date_notified']))
                answers.setdefault('third_conf_dt', f"{format_date(kp8[2]['hearing_date'])} @{format_time(kp8[2]['hearing_time'])}")
        
        # Build field mapping
        with connection.cursor() as cur:
            cur.execute("""SELECT f.field_id,LOWER(COALESCE(kff.label_override,f.base_label)),LOWER(f.field_code)
                           FROM kp_form_field kff JOIN kp_field f ON f.field_id=kff.field_id WHERE kff.form_id=%s""",[form_id])
            rows=cur.fetchall()
        by_label,by_code={},{}
        for fid,label,code in rows:
            val=answers.get(str(fid))
            if not val:
                val=answers.get(code)
            if isinstance(val,str): val=FS.sanitize_text(val)
            if val not in (None,"","null"):
                if label: by_label[label.strip().lower()]=val
                if code:  by_code[code.strip().lower()]=val
        def get(keys:Set[str])->str:
            for k in keys:
                if k in by_label: return FS.normalize(by_label[k])
                if k in by_code:  return FS.normalize(by_code[k])
            return ""
        out={t:get(s) for t,s in _SOURCES.items()}
        for k,v in list(out.items()):
            if isinstance(v,str): out[k]=FS.sanitize_text(v)
        for k in _FIELDS: out.setdefault(k,"")
        
        self._log(out); return out
