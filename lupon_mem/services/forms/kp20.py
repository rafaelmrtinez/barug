# lupon_mem/services/forms/kp20.py
from __future__ import annotations
from typing import Dict, Set, Optional, Tuple
from datetime import datetime as _dt, date as _date, time as _time
import json, logging, re
from django.db import connection
from zoneinfo import ZoneInfo
from .. import form_shared as FS

logger = logging.getLogger(__name__)

_KP20_FIELDS = [
    "complainants","respondents","brgy_case_number","purpose",
    "date_filed","time_filed","respondents_2",
    "complaint_date_month","complaint_year","by","ground_of",
    "this_date","this_month","this_year","lupon_sec","chairman",
]

_KP20_SOURCES: Dict[str, Set[str]] = {
    "complainants": {"complainants","complainant(s)"},
    "respondents": {"respondents","respondent(s)"},
    "respondents_2":{"respondents_2","respondents two"},
    "brgy_case_number":{"brgy_case_number","brgy_case_num","case number","case_no","blotter_case_num"},
    "purpose":{"purpose","for","case_purpose"},
    "date_filed":{"date_filed","filed_date","date_of_filing","date_created"},
    "time_filed":{"time_filed","filed_time","time_of_filing","time_created"},
    "complaint_date_month":{"complaint_date_month","month_of_complaint","current_month"},
    "complaint_year":{"complaint_year","year_of_complaint","current_year"},
    "by":{"by","issued_by","prepared_by"},
    "ground_of":{"ground_of","grounds","reason"},
    "this_date":{"this_date","current_date","date_today","date_entered"},
    "this_month":{"this_month","current_month","month_today","month_entered"},
    "this_year":{"this_year","current_year","year_today","year_entered"},
    "lupon_sec":{"lupon_sec","lupon secretary","secretary"},
    "chairman":{"chairman","punong barangay","barangay captain","brgy_capt"},
}

def _try_parse_date(s): 
    if not s: return None
    for fmt in ("%Y-%m-%d","%m/%d/%Y","%d/%m/%Y","%B %d, %Y"): 
        try: return _dt.strptime(s.strip(),fmt).date()
        except: pass
    return None

def _fmt_full(d:_date)->str: return d.strftime("%B %d, %Y")
def _fmt12(t:Optional[_time])->str:
    if not t: return ""
    return t.strftime("%I:%M %p").lstrip("0").lower()

def _parse_time(s:str)->Optional[_time]:
    if not s: return None
    try:
        s=s.strip().lower()
        if "am" in s or "pm" in s:
            return _dt.strptime(s.replace(".",""), "%I:%M %p").time()
        if ":" in s: return _dt.strptime(s, "%H:%M").time()
    except: pass
    return None

def _case_dt_by_case_num(case_num:str)->Tuple[Optional[_date],Optional[_time]]:
    if not case_num: return None,None
    with connection.cursor() as cur:
        cur.execute("SELECT date_filed,time_filed FROM blotter_case WHERE blotter_case_num=%s LIMIT 1",[case_num])
        row = cur.fetchone()
    return (row[0],row[1]) if row else (None,None)

def _case_dt_by_submission(submission_id:int)->Tuple[Optional[_date],Optional[_time],Optional[str]]:
    with connection.cursor() as cur:
        cur.execute("""
          SELECT bc.date_filed, bc.time_filed, bc.blotter_case_num
            FROM blotter_kp_submission s
            JOIN blotter_case bc ON bc.blotter_case_id = s.blotter_case_id
           WHERE s.submission_id=%s
        """,[submission_id])
        row = cur.fetchone()
    return (row[0],row[1],row[2]) if row else (None,None,None)

class KP20Handler:
    def _log(self,out:Dict[str,str])->None:
        try:
            ordered={k:out.get(k,"") for k in _KP20_FIELDS}
            print("[KP20] fill map (ordered):\n",json.dumps(ordered,ensure_ascii=False,indent=2))
            logger.info("KP20 fill map (ordered):\n%s",json.dumps(ordered,ensure_ascii=False,indent=2))
        except Exception as e:
            logger.warning("KP20 logging failed: %s",e)

    def build_name_value_map(self, form_id:int, submission_id:int)->dict:
        answers = FS.load_answers(submission_id)
        with connection.cursor() as cur:
            cur.execute("""
              SELECT f.field_id, LOWER(COALESCE(kff.label_override,f.base_label)), LOWER(f.field_code)
                FROM kp_form_field kff JOIN kp_field f ON f.field_id=kff.field_id
               WHERE kff.form_id=%s
            """,[form_id])
            rows = cur.fetchall()

        by_label:Dict[str,str]={}; by_code:Dict[str,str]={}
        for fid,label,code in rows:
            v = answers.get(str(fid))
            if isinstance(v,str): v = FS.sanitize_text(v)
            if v not in (None,"","null"):
                if label: by_label[label.strip().lower()] = v
                if code:  by_code[code.strip().lower()]  = v

        def find(keys:Set[str])->str:
            for k in keys:
                kk=k.strip().lower()
                if kk in by_label: return FS.normalize(by_label[kk])
                if kk in by_code:  return FS.normalize(by_code[kk])
            return ""

        out:Dict[str,str] = {t:find(s) for t,s in _KP20_SOURCES.items()}

        # case dt from DB
        case_num = (out.get("brgy_case_number") or "").strip()
        d_by_num,t_by_num = _case_dt_by_case_num(case_num) if case_num else (None,None)
        d_by_sub,t_by_sub,case_num_from_sub = _case_dt_by_submission(submission_id)
        if not case_num and case_num_from_sub:
            out["brgy_case_number"] = str(case_num_from_sub)

        d_ans = (out.get("date_filed") or "").strip()
        d_obj = _try_parse_date(d_ans) or d_by_num or d_by_sub or _dt.now(ZoneInfo("Asia/Manila")).date()
        out["date_filed"] = _fmt_full(d_obj)

        t_ans = (out.get("time_filed") or "").strip()
        t_obj = _parse_time(t_ans) or t_by_num or t_by_sub
        out["time_filed"] = _fmt12(t_obj) if t_obj else ""

        # complaint_date_month/year default to case filed month/year
        if not (out.get("complaint_date_month") or "").strip():
            out["complaint_date_month"] = d_obj.strftime("%B")
        if not (out.get("complaint_year") or "").strip():
            out["complaint_year"] = str(d_obj.year)

        # THIS trio defaults today
        today = _dt.now(ZoneInfo("Asia/Manila")).date()
        if not (out.get("this_date") or "").strip():  out["this_date"] = str(today.day)
        else:
            maybe = _try_parse_date(out["this_date"])
            if maybe: out["this_date"]=str(maybe.day)
        if not (out.get("this_month") or "").strip(): out["this_month"] = today.strftime("%B")
        if not (out.get("this_year") or "").strip():  out["this_year"]  = str(today.year)

        # sanitize + ensure keys
        for k,v in list(out.items()):
            if isinstance(v,str): out[k]=FS.sanitize_text(v)
        for k in _KP20_FIELDS: out.setdefault(k,"")

        self._log(out)
        return out
