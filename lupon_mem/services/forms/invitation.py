# lupon_mem/services/forms/invitation.py
from __future__ import annotations
from typing import Dict, Set
from datetime import datetime as _dt
from zoneinfo import ZoneInfo
import json, logging
from django.db import connection
from .. import form_shared as FS
logger = logging.getLogger(__name__)

_FIELDS = ["date_today","respondent_name","respondent_address","Text Box 1","venue","complainant_name"]
_SOURCES: Dict[str, Set[str]] = {
  "date_today":{"date_today","current_date"},
  "respondent_name":{"respondent_name","respondents"},
  "respondent_address":{"respondent_address","respondent_addr","address"},
  "Text Box 1":{"Text Box 1","body","message","details"},
  "venue":{"venue","place"},
  "complainant_name":{"complainant_name","complainants"},
}
def _today(): return _dt.now(ZoneInfo("Asia/Manila")).strftime("%B %d, %Y")

class InvitationHandler:
    def _log(self,out:Dict[str,str]):
        try: print("[INVITATION] fill map:\n", json.dumps({k:out.get(k,'') for k in _FIELDS}), ensure_ascii=False, indent=2)
        except Exception: pass

    def build_name_value_map(self, form_id:int, submission_id:int)->dict:
        answers = FS.load_answers(submission_id)
        with connection.cursor() as cur:
            cur.execute("""
              SELECT f.field_id, LOWER(COALESCE(kff.label_override,f.base_label)), LOWER(f.field_code)
              FROM kp_form_field kff JOIN kp_field f ON f.field_id=kff.field_id
              WHERE kff.form_id=%s
            """,[form_id]); rows = cur.fetchall()
        by_label,by_code = {},{}
        for fid,label,code in rows:
            val = answers.get(str(fid))
            if isinstance(val,str): val = FS.sanitize_text(val)
            if val not in (None,"","null"):
                if label: by_label[label.strip().lower()] = val
                if code:  by_code[code.strip().lower()]  = val
        def get(keys:Set[str])->str:
            for k in keys:
                if k in by_label: return FS.normalize(by_label[k])
                if k in by_code:  return FS.normalize(by_code[k])
            return ""
        out = {t:get(s) for t,s in _SOURCES.items()}
        if not out.get("date_today"): out["date_today"]=_today()
        for k,v in list(out.items()):
            if isinstance(v,str): out[k]=FS.sanitize_text(v)
        for k in _FIELDS: out.setdefault(k,"")
        self._log(out); return out
