# lupon_mem/services/forms/case_folder.py
from __future__ import annotations
from typing import Dict, Set
from datetime import datetime as _dt
from zoneinfo import ZoneInfo
import json, logging
from django.db import connection
from .. import form_shared as FS
logger = logging.getLogger(__name__)

_FIELDS = [
 "case_num","date_and_title","complainant_name","respondent_name","case_title","case_nature",
 "date_served","summon_date","date_first_hearing","mediation_remarks",
 "date_constitute_notice","date_notice_chosen_pangkat","date_notice_served","date_summon_served",
 "first_hearing_date","second_hearing_date","third_hearing_date","second_remarks",
 "agreement_arb_date","arb_served_date","arb_summ_served",
 "first_arb_hearing","second_arb_hearing","third_arb_hearing",
 "arb_remarks","dispo_sett_agrmnt","dispo_cfa","dispo_arb_award_date","dispo_refrd_date",
]
_SOURCES: Dict[str, Set[str]] = {
 "case_num":{"case_num","brgy_case_num","brgy_case_number"},
 "date_and_title":{"date_and_title"},
 "complainant_name":{"complainant_name","complainants"},
 "respondent_name":{"respondent_name","respondents"},
 "case_title":{"case_title","complaint_title","title"},
 "case_nature":{"case_nature","nature"},
 "date_served":{"date_served"},
 "summon_date":{"summon_date"},
 "date_first_hearing":{"date_first_hearing","first_hearing_date"},
 "mediation_remarks":{"mediation_remarks","remarks"},
 "date_constitute_notice":{"date_constitute_notice"},
 "date_notice_chosen_pangkat":{"date_notice_chosen_pangkat"},
 "date_notice_served":{"date_notice_served"},
 "date_summon_served":{"date_summon_served"},
 "first_hearing_date":{"first_hearing_date"},
 "second_hearing_date":{"second_hearing_date"},
 "third_hearing_date":{"third_hearing_date"},
 "second_remarks":{"second_remarks"},
 "agreement_arb_date":{"agreement_arb_date"},
 "arb_served_date":{"arb_served_date"},
 "arb_summ_served":{"arb_summ_served"},
 "first_arb_hearing":{"first_arb_hearing"},
 "second_arb_hearing":{"second_arb_hearing"},
 "third_arb_hearing":{"third_arb_hearing"},
 "arb_remarks":{"arb_remarks"},
 "dispo_sett_agrmnt":{"dispo_sett_agrmnt"},
 "dispo_cfa":{"dispo_cfa"},
 "dispo_arb_award_date":{"dispo_arb_award_date"},
 "dispo_refrd_date":{"dispo_refrd_date"},
}
def _today(fmt="%B %d, %Y"): return _dt.now(ZoneInfo("Asia/Manila")).strftime(fmt)

class CaseFolderHandler:
    def _log(self, out: Dict[str,str]):
        try:
            print("[CASE-FOLDER] fill map:\n", json.dumps({k:out.get(k,"") for k in _FIELDS}, ensure_ascii=False, indent=2))
        except Exception: pass

    def build_name_value_map(self, form_id:int, submission_id:int)->dict:
        answers = FS.load_answers(submission_id)
        with connection.cursor() as cur:
            cur.execute("""
              SELECT f.field_id, LOWER(COALESCE(kff.label_override,f.base_label)), LOWER(f.field_code)
              FROM kp_form_field kff JOIN kp_field f ON f.field_id=kff.field_id
              WHERE kff.form_id=%s
            """,[form_id])
            rows = cur.fetchall()
        by_label, by_code = {}, {}
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
        out = {t:get(srcs) for t,srcs in _SOURCES.items()}
        if not out.get("date_and_title"): out["date_and_title"]=_today()

        for k,v in list(out.items()):
            if isinstance(v,str): out[k]=FS.sanitize_text(v)
        for k in _FIELDS: out.setdefault(k,"")
        self._log(out)
        return out
