# lupon_mem/services/forms/med2_fta_set.py
from __future__ import annotations
from typing import Dict, Set
from datetime import datetime as _dt
from zoneinfo import ZoneInfo
import json, logging
from django.db import connection
from .. import form_shared as FS
logger=logging.getLogger(__name__)

_FIELDS = [
 "case_number","dt_filed","complainant_name","respondent_name","complaint_title","case_nature",
 "first_hearing_dt","second_hearing_dt","third_hearing_dt",
 "first_summ_dt","first_offcret_dt","second_summ_dt","second_offcret_dt",
 "third_summ_dt","third_officret_dt","first_conf_dt",
 "failure_to_appear","fta_reason","form_nineteen_dt","second_fta_reason","second_conf","second_conf_dt",
 "main_agreement","exec_dt","report_to_court_dt","report_to_dilg_dt","monitoring_dt","monitoring_remarks",
]
_SOURCES: Dict[str, Set[str]] = {k:{k} for k in _FIELDS}
_SOURCES.update({
 "complainant_name":{"complainant_name","complainants"},
 "respondent_name":{"respondent_name","respondents"},
 "complaint_title":{"complaint_title","case_title","title"},
})
def _today(fmt="%B %d, %Y"): return _dt.now(ZoneInfo("Asia/Manila")).strftime(fmt)

class Med2FtaSettledHandler:
    def _log(self,out:Dict[str,str]):
        try: print("[MED2-FTA-SET] fill map:\n", json.dumps({k:out.get(k,'') for k in _FIELDS}, ensure_ascii=False, indent=2))
        except Exception: pass

    def build_name_value_map(self, form_id:int, submission_id:int)->dict:
        answers=FS.load_answers(submission_id)
        with connection.cursor() as cur:
            cur.execute("""SELECT f.field_id,LOWER(COALESCE(kff.label_override,f.base_label)),LOWER(f.field_code)
                           FROM kp_form_field kff JOIN kp_field f ON f.field_id=kff.field_id WHERE kff.form_id=%s""",[form_id])
            rows=cur.fetchall()
        by_label,by_code={},{}
        for fid,label,code in rows:
            val=answers.get(str(fid))
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
