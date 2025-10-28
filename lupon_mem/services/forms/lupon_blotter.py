from __future__ import annotations
# lupon_mem/services/forms/lupon_blotter.py
from typing import Dict, Set
import json, logging
from django.db import connection
from .. import form_shared as FS
logger = logging.getLogger(__name__)

_FIELDS = [
  "brgy_blotter_case_number","date_time",
  "complainant_name","complainant_addr","complainant_contact_num",
  "respondent_name","respondent_addr","respondent_contact_num",
  "date_time_of_incident","incident_information",
  "complainant_printed_name","lupon_tagapamayapa","brgy_captain","brgy_sec",
]
_SOURCES: Dict[str, Set[str]] = {
  "brgy_blotter_case_number":{"brgy_blotter_case_number","case_num","brgy_case_num"},
  "date_time":{"date_time","date_filed","time_filed"},
  "complainant_name":{"complainant_name","complainants"},
  "complainant_addr":{"complainant_addr","complainant_address"},
  "complainant_contact_num":{"complainant_contact_num","complainant_contact"},
  "respondent_name":{"respondent_name","respondents"},
  "respondent_addr":{"respondent_addr","respondent_address"},
  "respondent_contact_num":{"respondent_contact_num","respondent_contact"},
  "date_time_of_incident":{"date_time_of_incident"},
  "incident_information":{"incident_information","incident_details","details"},
  "complainant_printed_name":{"complainant_printed_name"},
  "lupon_tagapamayapa":{"lupon_tagapamayapa","lupon_tagapamayap"},
  "brgy_captain":{"brgy_captain","brgy_capt"},
  "brgy_sec":{"brgy_sec"},
}

class LuponBlotterHandler:
    def _log(self,out:Dict[str,str]):
        try: print("[LUPON-BLOTTER] fill map:\n", json.dumps({k:out.get(k,'') for k in _FIELDS}, ensure_ascii=False, indent=2))
        except Exception: pass

    def build_name_value_map(self, form_id:int, submission_id:int)->dict:
        answers=FS.load_answers(submission_id)
        with connection.cursor() as cur:
            cur.execute("""
              SELECT f.field_id, LOWER(COALESCE(kff.label_override,f.base_label)), LOWER(f.field_code)
              FROM kp_form_field kff JOIN kp_field f ON f.field_id=kff.field_id
              WHERE kff.form_id=%s
            """,[form_id]); rows=cur.fetchall()
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
