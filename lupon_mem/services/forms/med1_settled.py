# lupon_mem/services/forms/med1_settled.py
from __future__ import annotations
from typing import Dict, Set
import json, logging
from django.db import connection
from .. import form_shared as FS

logger = logging.getLogger(__name__)

_FIELDS = [
    "case_num","dt_filed","complainant_name","respondent_name","complaint_title","case_nature",
    "first_notice_dt","second_notice_dt","third_notice_dt",
    "first_summon_dt","officer_return_dt",
    "second_summon_dt","officer_return_dt2",
    "third_summon_dt","third_offret_dt",
    "first_conf_dt","settlement_dt",
    "Text Box 1",
    "monitoring_remarks",
    "dt_exec","dt_court_report","dt_report_dilg","monitoring_date",
]

_SOURCES: Dict[str, Set[str]] = {k: {k} for k in _FIELDS}
_SOURCES.update({
    "case_num":         {"case_num","brgy_case_num","case_number","case number"},
    "complainant_name": {"complainant_name","complainants","complainant name"},
    "respondent_name":  {"respondent_name","respondents","respondent name"},
    "complaint_title":  {"complaint_title","case_title","title","complaint title"},
    "case_nature":      {"case_nature","case nature"},
    "dt_filed":         {"dt_filed","date & time filed","date and time filed"},
    "first_notice_dt":  {"first_notice_dt","1st notice date"},
    "second_notice_dt": {"second_notice_dt","2nd notice date"},
    "third_notice_dt":  {"third_notice_dt","3rd notice date"},
    "first_summon_dt":  {"first_summon_dt","1st summons date"},
    "officer_return_dt": {"officer_return_dt","officer's return date (1)"},
    "second_summon_dt": {"second_summon_dt","2nd summons date"},
    "officer_return_dt2": {"officer_return_dt2","officer's return date (2)"},
    "third_summon_dt":  {"third_summon_dt","3rd summons date"},
    "third_offret_dt":  {"third_offret_dt","officer's return date (3)"},
    "first_conf_dt":    {"first_conf_dt","1st conference date"},
    "settlement_dt":    {"settlement_dt","settlement date"},
    "Text Box 1":       {"text box 1","notes"},
    "monitoring_remarks": {"monitoring_remarks","monitoring remarks"},
    "dt_exec":          {"dt_exec","execution date"},
    "dt_court_report":  {"dt_court_report","report to court date"},
    "dt_report_dilg":   {"dt_report_dilg","report to dilg date"},
    "monitoring_date":  {"monitoring_date","monitoring date"},
})

class Med1SettledHandler:
    def build_name_value_map(self, form_id: int, submission_id: int) -> dict:
        answers = FS.load_answers(submission_id)
        with connection.cursor() as cur:
            cur.execute("""
                SELECT f.field_id, LOWER(COALESCE(kff.label_override, f.base_label)), LOWER(f.field_code)
                FROM kp_form_field kff
                JOIN kp_field f ON f.field_id = kff.field_id
                WHERE kff.form_id = %s
            """, [form_id])
            rows = cur.fetchall()
        
        by_label, by_code = {}, {}
        for fid, label, code in rows:
            val = answers.get(str(fid))
            if isinstance(val, str):
                val = FS.sanitize_text(val)
            if val not in (None, "", "null"):
                if label:
                    by_label[label.strip().lower()] = val
                if code:
                    by_code[code.strip().lower()] = val
        
        def get(keys):
            for k in keys:
                if k in by_label:
                    return FS.normalize(by_label[k])
                if k in by_code:
                    return FS.normalize(by_code[k])
            return ""
        
        out = {t: get(s) for t, s in _SOURCES.items()}
        for k, v in list(out.items()):
            if isinstance(v, str):
                out[k] = FS.sanitize_text(v)
        for k in _FIELDS:
            out.setdefault(k, "")
        
        print("[MED1-SETTLED] UI-only:", json.dumps({k: out.get(k, "") for k in _FIELDS}, ensure_ascii=False, indent=2))
        return out
