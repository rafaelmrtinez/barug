# lupon_mem/services/forms/kp19.py
from __future__ import annotations
from typing import Dict, Set, Optional, Tuple
from datetime import datetime as _dt, date as _date, time as _time
import json, logging, re

from django.db import connection
from zoneinfo import ZoneInfo
from .. import form_shared as FS
from .util import get_lupon_chair_name  # Pangkat Chairman (Lupon Chair/President)

logger = logging.getLogger(__name__)

_KP19_FIELDS = [
    "complainants","respondents","brgy_case_number","purpose",
    "date_filed","time_filed",
    "repondents_two",
    "appearance_date","appearance_month","appearance_year","appearance_time",
    "date_month_scheduled","year_scheduled",
    "this_date","this_month","this_year",
    "chairman",
    "date_notified","month_notified","year_notified",
    "complainants_two","respondents_three",
]

_KP19_SOURCES: Dict[str, Set[str]] = {
    "complainants": {"complainants","complainant(s)","party-complainants","parties_complainants"},
    "complainants_two": {"complainants_two","complainants 2","complainant_two","complainant 2","party-complainants-2"},
    "respondents": {"respondents","respondent(s)","party-respondents","parties_respondents"},
    "repondents_two": {"repondents_two","respondents_two","respondents 2","respondent_two","respondent 2","party-respondents-2"},
    "respondents_three": {"respondents_three","respondents 3","respondent_three","respondent 3"},
    "brgy_case_number": {"brgy_case_number","brgy_case_num","case number","case_no","case_num","blotter_case_num"},
    "purpose": {"purpose","for","case_purpose"},

    # case filed (answers may exist; DB is source of truth)
    "date_filed": {"date_filed","filed_date","date_of_filing","date_created","date today","date_today"},
    "time_filed": {"time_filed","filed_time","time_of_filing","time_created"},

    # appearance/schedule pieces
    "appearance_date": {"appearance_date","hearing_date","schedule_date","day_of","appearance_day"},
    "appearance_month":{"appearance_month","appearance_mo","hearing_month","month_of_hearing","schedule_month"},
    "appearance_year": {"appearance_year","current_year","hearing_year","schedule_year"},
    "appearance_time": {"appearance_time","hearing_time","schedule_time"},

    # header schedule (we’ll overwrite from latest hearing)
    "date_month_scheduled": {"date_month_scheduled","appearance_month","hearing_month","schedule_month"},
    "year_scheduled": {"year_scheduled","appearance_year","current_year","hearing_year","schedule_year"},

    # “this” (entry) date
    "this_date": {"this_date","date_entered","current_date","date_today"},
    "this_month":{"this_month","month_entered","current_month","month_today"},
    "this_year": {"this_year","year_entered","current_year","year_today"},

    # Notified date trio
    "date_notified": {"date_notified","served_date","service_date"},
    "month_notified":{"month_notified","served_month","service_month"},
    "year_notified": {"year_notified","served_year","service_year"},

    # Chairman
    "chairman": {},
}

# ---------- helpers ----------
def _try_parse_date(s:str)->Optional[_date]:
    if not s: return None
    for fmt in ("%Y-%m-%d","%m/%d/%Y","%d/%m/%Y","%B %d, %Y","%b %d, %Y","%d %B %Y","%d %b %Y"):
        try: return _dt.strptime(s.strip(),fmt).date()
        except: pass
    return None

def _month_to_num(m:str)->Optional[int]:
    if not m: return None
    for fmt in ("%B","%b"):
        try: return _dt.strptime(m.strip(),fmt).month
        except: pass
    return None

def _fmt_full(d:_date)->str: return d.strftime("%B %d, %Y")

def _fmt12(t:Optional[_time])->str:
    if not t: return ""
    s = t.strftime("%I:%M %p").lstrip("0").lower()
    return s

def _parse_time(s:str)->Optional[_time]:
    if not s: return None
    txt = re.sub(r"\s+"," ",s.strip().lower())
    m = re.match(r"^(\d{1,2}):(\d{1,2})(?::\d{1,2})?\s*([ap]\.?m\.?)?$", txt)
    if m:
        hh,mm,ap = m.groups(); mm=f"{int(mm):02d}"
        if ap:
            ap=ap.replace(".","")
            try: return _dt.strptime(f"{int(hh)}:{mm} {ap}","%I:%M %p").time()
            except: pass
        else:
            try: return _dt.strptime(f"{int(hh):02d}:{mm}","%H:%M").time()
            except: pass
    for fmt in ("%H:%M","%H:%M:%S","%I:%M %p","%I:%M%p","%I %p"):
        try: return _dt.strptime(txt,fmt).time()
        except: pass
    return None

# ---------- DB lookups ----------
def _case_dt_by_case_num(case_num:str)->Tuple[Optional[_date],Optional[_time]]:
    if not case_num: return None,None
    with connection.cursor() as cur:
        cur.execute("""SELECT date_filed,time_filed FROM blotter_case WHERE blotter_case_num=%s LIMIT 1""",[case_num])
        row = cur.fetchone()
    return (row[0],row[1]) if row else (None,None)

def _case_dt_by_submission(submission_id:int)->Tuple[Optional[_date],Optional[_time],Optional[str],Optional[int]]:
    with connection.cursor() as cur:
        cur.execute("""
          SELECT bc.date_filed, bc.time_filed, bc.blotter_case_num, bc.blotter_case_id
            FROM blotter_kp_submission s
            JOIN blotter_case bc ON bc.blotter_case_id = s.blotter_case_id
           WHERE s.submission_id=%s
        """,[submission_id])
        row = cur.fetchone()
    return (row[0],row[1],row[2],row[3]) if row else (None,None,None,None)

def _latest_hearing_date_for_case(case_id:int)->Optional[_date]:
    if not case_id: return None
    with connection.cursor() as cur:
        cur.execute("""
            SELECT hearing_date
              FROM fn_case_mediation_hearings(%s)
             WHERE COALESCE(NULLIF(TRIM(hearing_date), ''), NULL) IS NOT NULL
             ORDER BY (hearing_date)::date DESC, notice_created_at DESC
             LIMIT 1
        """,[case_id])
        row = cur.fetchone()
    if not row: return None
    txt = str(row[0]).strip()
    try:
        return _dt.strptime(txt, "%Y-%m-%d").date()
    except:
        return _try_parse_date(txt)

# ---------- handler ----------
class KP19Handler:
    @staticmethod
    def _log_fill_map(out:Dict[str,str])->None:
        try:
            ordered={k:out.get(k,"") for k in _KP19_FIELDS}
            print("[KP19] fill map (ordered):\n", json.dumps(ordered, ensure_ascii=False, indent=2))
            logger.info("KP19 fill map (ordered):\n%s", json.dumps(ordered, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.warning("KP19 logging failed: %s", e)

    def build_name_value_map(self, form_id:int, submission_id:int)->dict:
        answers = FS.load_answers(submission_id)

        # discover labels/codes on this form
        with connection.cursor() as cur:
            cur.execute("""
              SELECT f.field_id,
                     LOWER(COALESCE(kff.label_override, f.base_label)) AS label,
                     LOWER(f.field_code) AS code
                FROM kp_form_field kff
                JOIN kp_field f ON f.field_id = kff.field_id
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

        out:Dict[str,str] = { tgt:find(srcs) for tgt,srcs in _KP19_SOURCES.items() }

        # party mirrors
        if not (out.get("complainants_two") or "").strip():
            out["complainants_two"] = out.get("complainants","")
        if not (out.get("repondents_two") or "").strip():
            out["repondents_two"] = out.get("respondents","")
        if not (out.get("respondents_three") or "").strip():
            out["respondents_three"] = out.get("respondents","")

        # case date/time via case number or submission (also grab case_id)
        case_num = (out.get("brgy_case_number") or "").strip()
        d_by_num,t_by_num = _case_dt_by_case_num(case_num) if case_num else (None,None)
        d_by_sub,t_by_sub,case_num_from_sub,case_id = _case_dt_by_submission(submission_id)
        if not case_num and case_num_from_sub:
            out["brgy_case_number"] = str(case_num_from_sub)

        # date_filed
        d_ans = (out.get("date_filed") or "").strip()
        d_obj = _try_parse_date(d_ans) or d_by_num or d_by_sub or _dt.now(ZoneInfo("Asia/Manila")).date()
        out["date_filed"] = _fmt_full(d_obj)

        # time_filed
        t_ans = (out.get("time_filed") or "").strip()
        t_obj = _parse_time(t_ans) or t_by_num or t_by_sub
        out["time_filed"] = _fmt12(t_obj) if t_obj else ""

        # appearance date – compose from parts if needed
        ph_today = _dt.now(ZoneInfo("Asia/Manila")).date()
        ad_txt = (out.get("appearance_date") or "").strip()
        am_txt = (out.get("appearance_month") or "").strip()
        ay_txt = (out.get("appearance_year") or "").strip()

        ad_obj = _try_parse_date(ad_txt)
        if not ad_obj:
            if ad_txt.isdigit() and (m:=_month_to_num(am_txt)) and ay_txt.isdigit():
                try: ad_obj = _date(int(ay_txt),m,int(ad_txt))
                except: ad_obj = None
        if not ad_obj:
            m_num = _month_to_num(am_txt)
            if m_num and ay_txt.isdigit():
                try: ad_obj = _date(int(ay_txt), m_num, ph_today.day)
                except: pass
        if not ad_obj: ad_obj = ph_today

        out["appearance_date"]  = str(ad_obj.day)
        out["appearance_month"] = ad_obj.strftime("%B")
        out["appearance_year"]  = str(ad_obj.year)

        # date_month_scheduled/year_scheduled → USE LATEST HEARING DATE
        latest = _latest_hearing_date_for_case(case_id) if case_id else None
        if latest:
            out["date_month_scheduled"] = f"{latest.strftime('%B')} {latest.day}"   # Month DD
            out["year_scheduled"] = str(latest.year)                                # YYYY
        else:
            # fallback mirrors final appearance date
            out["date_month_scheduled"] = f"{ad_obj.strftime('%B')} {ad_obj.day}"
            out["year_scheduled"] = str(ad_obj.year)

        # appearance_time: keep given; else fallback to case time
        at = _parse_time(out.get("appearance_time",""))
        if not at and t_obj: at = t_obj
        out["appearance_time"] = _fmt12(at) if at else ""

        # THIS date trio defaults today
        if not (out.get("this_date") or "").strip():
            out["this_date"] = str(ph_today.day)
        else:
            maybe = _try_parse_date(out["this_date"])
            if maybe: out["this_date"] = str(maybe.day)
        if not (out.get("this_month") or "").strip():
            out["this_month"] = ph_today.strftime("%B")
        if not (out.get("this_year") or "").strip():
            out["this_year"]  = str(ph_today.year)

        # Notified trio defaults today
        if not (out.get("date_notified") or "").strip():
            out["date_notified"] = str(ph_today.day)
        else:
            maybe = _try_parse_date(out["date_notified"])
            if maybe: out["date_notified"] = str(maybe.day)
        if not (out.get("month_notified") or "").strip():
            out["month_notified"] = ph_today.strftime("%B")
        if not (out.get("year_notified") or "").strip():
            out["year_notified"] = str(ph_today.year)

        # Pangkat Chairman (auto-fill like KP-13/KP-18)
        if not (out.get("chairman") or "").strip():
            out["chairman"] = get_lupon_chair_name(default=out.get("chairman",""))

        # sanitize + ensure fields exist
        for k,v in list(out.items()):
            if isinstance(v,str): out[k]=FS.sanitize_text(v)
        for k in _KP19_FIELDS: out.setdefault(k,"")

        # KP-18–style final ordered log of exactly what goes into the PDF
        self._log_fill_map(out)
        return out
