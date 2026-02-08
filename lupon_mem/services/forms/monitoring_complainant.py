# lupon_mem/services/forms/monitoring_complainant.py
from __future__ import annotations
from typing import Dict
import json, logging
from django.db import connection
from .. import form_shared as FS
logger=logging.getLogger(__name__)

_FIELDS = [
 "brgy_case_num","date_time_monitoring",
 "complainant_name","complainant_addr","complainant_contact",
 "respondent_name","respondent_addr","respondent_contact",
 "remarks","complainant_printed_name","lupon_tagapamayap","brgy_capt","brgy_sec"
]

# Map PDF field names to database field IDs
_FIELD_ID_MAP = {
    "brgy_case_num": 23,
    "date_time_monitoring": 190,
    "complainant_name": 1,
    "complainant_addr": 139,
    "complainant_contact": 35,
    "respondent_name": 2,
    "respondent_addr": 85,
    "respondent_contact": 178,
    "remarks": 110,
    "complainant_printed_name": 10,
    "lupon_tagapamayap": 177,
    "brgy_capt": 104,
    "brgy_sec": 208,
}

class MonitoringComplainantHandler:
    def _log(self,out:Dict[str,str]):
        try: print("[MON-COMPL] fill map:\n", json.dumps({k:out.get(k,'') for k in _FIELDS}, ensure_ascii=False, indent=2))
        except Exception: pass

    def build_name_value_map(self, form_id:int, submission_id:int)->dict:
        answers=FS.load_answers(submission_id)
        print(f"[MON-COMPL] Raw answers from DB: {answers}")
        out={}
        for pdf_field, field_id in _FIELD_ID_MAP.items():
            val = answers.get(str(field_id))
            if isinstance(val,str): 
                val=FS.sanitize_text(val)
                # Filter out values that look like field labels
                if val and any(x in val.lower() for x in ['complainant', 'respondent', 'monitoring', 'address', 'contact', 'printed name', 'lupon', 'barangay', 'remarks', 'punong']):
                    if val.count(' ') >= 2:  # Labels usually have multiple words
                        val = ""
            if val not in (None,"","null"):
                out[pdf_field] = FS.normalize(val)
            else:
                out[pdf_field] = ""
        
        # Defaults
        for k in _FIELDS: out.setdefault(k,"")
        if not out.get("brgy_sec"): out["brgy_sec"]="JUDE FRENCILLO"
        
        self._log(out)
        return out
