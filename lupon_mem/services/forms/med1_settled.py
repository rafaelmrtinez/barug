# lupon_mem/services/forms/med1_settled.py
from __future__ import annotations
from typing import Dict, Set, Tuple, List, Optional
from datetime import datetime as _dt, date as _date, time as _time
from zoneinfo import ZoneInfo
import json, logging
from django.db import connection
from .. import form_shared as FS

logger = logging.getLogger(__name__)

# Turn off once verified
DUMMY_MODE = False

_FIELDS = [
    "case_num","dt_filed","complainant_name","respondent_name","complaint_title","case_nature",

    # NOTICES (KP-8/KP-12 schedules)
    "first_notice_dt","second_notice_dt","third_notice_dt",

    # SUMMONS (KP-9)
    "first_summon_dt","officer_return_dt",
    "second_summon_dt","officer_return_dt2",
    "third_summon_dt","third_offret_dt",

    # ACTION TAKEN
    "first_conf_dt","settlement_dt",

    # MAIN POINT + MONITORING
    "Text Box 1",                 # main point of agreement / body
    "monitoring_remarks",
    "dt_exec","dt_court_report","dt_report_dilg","monitoring_date",
]

_SOURCES: Dict[str, Set[str]] = {k: {k} for k in _FIELDS}
_SOURCES.update({
    "case_num":         {"case_num","brgy_case_num","case_number"},
    "complainant_name": {"complainant_name","complainants"},
    "respondent_name":  {"respondent_name","respondents"},
    "complaint_title":  {"complaint_title","case_title","title"},
})

def _today(fmt="%B %d, %Y") -> str:
    return _dt.now(ZoneInfo("Asia/Manila")).strftime(fmt)

def _format_dt(date_iso: Optional[str], time_hm: Optional[str]) -> str:
    """
    Best-effort "Month DD, YYYY HH:MM AM/PM" from pieces like '2025-10-16' + '14:30'
    Falls back to whatever non-empty value we have.
    """
    if date_iso and len(date_iso) >= 8:
        try:
            d = _dt.strptime(date_iso[:10], "%Y-%m-%d").date()
            if time_hm:
                try:
                    t = _dt.strptime(time_hm, "%H:%M").time()
                    return f"{d.strftime('%B %d, %Y')} {t.strftime('%I:%M %p').lstrip('0')}"
                except Exception:
                    return f"{d.strftime('%B %d, %Y')} {time_hm}"
            return d.strftime("%B %d, %Y")
        except Exception:
            pass
    if date_iso and time_hm:
        return f"{date_iso} {time_hm}"
    return date_iso or time_hm or ""

def _first_nonblank(*vals) -> str:
    for v in vals:
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""

class Med1SettledHandler:
    # ---------------- core util: fetch case_id from this MED1 submission ----------------
    def _case_id_for_submission(self, submission_id: int) -> Optional[int]:
        with connection.cursor() as cur:
            cur.execute("SELECT blotter_case_id FROM blotter_kp_submission WHERE submission_id=%s", [submission_id])
            r = cur.fetchone()
            return int(r[0]) if r and r[0] else None

    # ---------------- fetch all submissions for form code (newest first) ----------------
    def _submissions_for_code(self, case_id: int, code: str) -> List[Tuple[int, int]]:
        """
        Returns list of (form_id, submission_id) for the case, filtered by form code (UPPER),
        ordered by submitted_at DESC, submission_id DESC.
        """
        with connection.cursor() as cur:
            cur.execute("""
                WITH wanted AS (
                  SELECT form_id FROM kp_form WHERE UPPER(form_code)=UPPER(%s) LIMIT 1
                )
                SELECT s.form_id, s.submission_id
                FROM blotter_kp_submission s
                JOIN wanted w ON w.form_id = s.form_id
                WHERE s.blotter_case_id = %s
                ORDER BY (UPPER(s.status)='SUBMITTED') DESC,
                         s.submitted_at DESC NULLS LAST,
                         s.submission_id DESC
            """, [code, case_id])
            return [(int(f), int(s)) for f, s in cur.fetchall()]

    # ------------- fetch a single submission’s answers keyed by lower(field_code) -------
    def _answers_by_code(self, form_id: int, submission_id: int) -> Dict[str, str]:
        with connection.cursor() as cur:
            cur.execute("""
                SELECT LOWER(f.field_code) AS code_lc,
                       TRIM(BOTH '"' FROM a.value_json::text) AS value_txt
                FROM blotter_kp_answer a
                JOIN kp_field f ON f.field_id = a.field_id
                WHERE a.submission_id = %s
            """, [submission_id])
            rows = cur.fetchall()
        out = {}
        for code, val in rows:
            if not code:
                continue
            out[code] = FS.sanitize_text(val or "")
        return out

    # ------------- fetch a single submission’s answers keyed by lower(label) ------------
    def _answers_by_label(self, form_id: int, submission_id: int) -> Dict[str, str]:
        """
        Returns answers keyed by LOWER(label) where label = kff.label_override or f.base_label.
        """
        with connection.cursor() as cur:
            cur.execute("""
                SELECT LOWER(COALESCE(NULLIF(kff.label_override,''), f.base_label)) AS label_lc,
                       TRIM(BOTH '"' FROM a.value_json::text) AS value_txt
                  FROM kp_form_field kff
                  JOIN kp_field f        ON f.field_id = kff.field_id
                  LEFT JOIN blotter_kp_answer a
                    ON a.field_id = kff.field_id AND a.submission_id = %s
                 WHERE kff.form_id = %s
            """, [submission_id, form_id])
            rows = cur.fetchall()
        out = {}
        for lbl, val in rows:
            if not lbl:
                continue
            out[lbl] = FS.sanitize_text(val or "")
        return out

    # ---------------- KP-8 / KP-12 schedules (date/time) in chronological order ----------
    def _notice_schedule_triplet(self, case_id: int) -> List[Tuple[str, str, str, str]]:
        """
        Returns up to 3 (notice_date, notice_time, hearing_date, hearing_time) for KP-8/KP-12.
        """
        pairs: List[Tuple[str, str, str, str, _dt, int]] = []
        with connection.cursor() as cur:
            cur.execute("""
                WITH forms AS (
                  SELECT form_id, UPPER(form_code) AS code
                    FROM kp_form
                   WHERE UPPER(form_code) IN ('KP-8','KP-12')
                )
                SELECT s.submission_id, s.form_id, s.submitted_at
                  FROM blotter_kp_submission s
                  JOIN forms f ON f.form_id = s.form_id
                 WHERE s.blotter_case_id = %s
            """, [case_id])
            rows = cur.fetchall()

        for sid, fid, sub_at in rows:
            bycode = self._answers_by_code(fid, sid)
            notice_d = _first_nonblank(bycode.get("processed_on_date"), bycode.get("appearance_date"))
            notice_t = _first_nonblank(bycode.get("hearing_time"), bycode.get("appearance_time"))
            hearing_d = _first_nonblank(bycode.get("hearing_date"), bycode.get("appearance_date"))
            hearing_t = _first_nonblank(bycode.get("hearing_time"), bycode.get("appearance_time"))
            if notice_d or notice_t or hearing_d or hearing_t:
                pairs.append((notice_d, notice_t, hearing_d, hearing_t, sub_at or _dt.now(), sid))

        pairs.sort(key=lambda r: (r[4], r[5]))
        out = [(nd, nt, hd, ht) for (nd, nt, hd, ht, _, __) in pairs[:3]]
        print("[MED1-SETTLED][NOTICES] triplet raw =", json.dumps(out))
        return out

    # ---------------- KP-9 summons up to 3 (date/time + officer return) -----------------
    def _summons_triplet(self, case_id: int):
        """
        Returns up to 3 summons entries with officer return dates.
        Matches KP-9 summons with their corresponding officer return from any submission.
        """
        results = []
        
        # Get all submissions for this case to find officer return dates
        with connection.cursor() as cur:
            cur.execute("""
                SELECT a.submission_id, LOWER(f.field_code) AS code_lc,
                       TRIM(BOTH '"' FROM a.value_json::text) AS value_txt
                FROM blotter_kp_submission s
                JOIN blotter_kp_answer a ON a.submission_id = s.submission_id
                JOIN kp_field f ON f.field_id = a.field_id
                WHERE s.blotter_case_id = %s AND LOWER(f.field_code) = 'date_offcret'
            """, [case_id])
            offret_data = {row[0]: row[2] for row in cur.fetchall()}
        
        print(f"[MED1-SETTLED][OFFRET-DEBUG] Found officer returns: {offret_data}")
        
        kp9s = self._submissions_for_code(case_id, "KP-9")
        kp9_2s = self._submissions_for_code(case_id, "KP-9-2")
        all_summons = kp9s + kp9_2s
        all_summons = list(reversed(all_summons))
        
        for fid, sid in all_summons:
            bycode = self._answers_by_code(fid, sid)
            d = _first_nonblank(bycode.get("curr_date"), bycode.get("processed_on_date"), bycode.get("summon_date"), bycode.get("appearance_date"), bycode.get("date"))
            t = _first_nonblank(bycode.get("processed_on_time"), bycode.get("summon_time"), bycode.get("appearance_time"), bycode.get("time"))
            dt_text = _format_dt(d, t)

            # Check if this submission or next submission has officer return
            off_d = bycode.get("date_offcret", "")
            if not off_d and (sid + 1) in offret_data:
                off_d = offret_data[sid + 1]
            off_t = bycode.get("time_offcret", "")
            off_text = _format_dt(off_d, off_t)

            results.append({"dt": dt_text, "offret": off_text})
            if len(results) >= 3:
                break

        print("[MED1-SETTLED][SUMMONS] =", json.dumps(results, ensure_ascii=False))
        # Ensure length 3 with blanks
        while len(results) < 3:
            results.append({"dt": "", "offret": ""})
        return results[:3]

    # ---------------- KP-16 content: main points + settlement date ----------------------
    def _kp16_main_and_date(self, case_id: int) -> Tuple[str, str]:
        """
        Returns (main_text, settlement_dt_text).
        MAIN TEXT strictly prefers the 'settlement_statement' field (by code or label),
        then other reasonable fallbacks.
        """
        kp16s = self._submissions_for_code(case_id, "KP-16")
        if not kp16s:
            return "", ""

        fid, sid = kp16s[0]  # newest
        bycode  = self._answers_by_code(fid, sid)
        bylabel = self._answers_by_label(fid, sid)

        # 1) STRICT PREFERENCE: settlement_statement
        PREFERRED_CODE_KEYS  = ["settlement_statement", "settlement_agreement", "agreement_text"]
        PREFERRED_LABEL_KEYS = [
            "settlement statement",
            "settlement agreement",
            "main point of agreement",
            "main points of agreement",
        ]

        main_text = ""
        for k in PREFERRED_CODE_KEYS:
            if k in bycode and bycode[k].strip():
                main_text = bycode[k].strip()
                break
        if not main_text:
            for k in PREFERRED_LABEL_KEYS:
                if k in bylabel and bylabel[k].strip():
                    main_text = bylabel[k].strip()
                    break

        # 2) GENERIC FALLBACKS if the preferred field is not present
        if not main_text:
            GENERIC_CODE = ["agreement", "main_points", "main_point", "settlement_text",
                            "text box 1", "text_box_1", "details", "remarks", "body"]
            for k in GENERIC_CODE:
                if k in bycode and bycode[k].strip():
                    main_text = bycode[k].strip()
                    break
        if not main_text and bylabel:
            # take the longest label answer as last resort
            main_text = max(bylabel.values(), key=lambda s: len(s or ""), default="")

        # Settlement date: prefer explicit KP-16 fields, else use submitted_at
        with connection.cursor() as cur:
            cur.execute("SELECT submitted_at FROM blotter_kp_submission WHERE submission_id=%s", [sid])
            r = cur.fetchone()
            submitted_at = r[0] if r else None

        settle_d = _first_nonblank(bycode.get("settlement_date"), bycode.get("date_signed"), bycode.get("date"))
        settle_t = _first_nonblank(bycode.get("settlement_time"), bycode.get("time"))
        if not (settle_d or settle_t):
            if submitted_at:
                try:
                    settle_d = submitted_at.strftime("%Y-%m-%d")
                    settle_t = submitted_at.strftime("%H:%M")
                except Exception:
                    pass

        dt_text = _format_dt(settle_d, settle_t)

        # DEBUG
        print("[MED1-SETTLED][KP16] picked settlement_statement?",
              any(k in bycode for k in PREFERRED_CODE_KEYS),
              " len(body)=", len(main_text or ""), " dt=", dt_text)

        return main_text or "", dt_text or ""

    # ---------------- Case header: parties, titles, dates --------------------------------
    def _case_header(self, case_id: int) -> dict:
        out = {
            "case_num": "", "dt_filed": "", "complaint_title": "", "case_nature": "",
            "complainant_name": "", "respondent_name": "",
        }
        with connection.cursor() as cur:
            cur.execute("""
                SELECT bc.blotter_case_num,
                       bc.date_filed, bc.time_filed,
                       COALESCE(ct.complaint_title_name,''),
                       COALESCE(cn.case_name,'')
                FROM blotter_case bc
                LEFT JOIN complaint_title ct ON ct.complaint_title_id = bc.complaint_title_id
                LEFT JOIN case_nature cn     ON cn.case_nature_id     = bc.case_nature_id
                WHERE bc.blotter_case_id=%s
            """, [case_id])
            r = cur.fetchone()
        if r:
            case_no, d_filed, t_filed, title, nature = r
            out["case_num"] = case_no or ""
            out["dt_filed"] = _format_dt(d_filed.isoformat() if hasattr(d_filed, "isoformat") else "", 
                                         t_filed.strftime("%H:%M") if hasattr(t_filed, "strftime") else "")
            out["complaint_title"] = title or ""
            out["case_nature"] = nature or ""

        # parties
        with connection.cursor() as cur:
            cur.execute("""
                SELECT trim(coalesce(p.first_name,'') || ' ' || coalesce(p.last_name,'')) AS name
                FROM complainant_case cc
                JOIN person p ON p.person_id = cc.person_id
                WHERE cc.blotter_case_id=%s
                ORDER BY name
            """, [case_id])
            cmps = [r[0] for r in cur.fetchall()]
            cur.execute("""
                SELECT trim(coalesce(p.first_name,'') || ' ' || coalesce(p.last_name,'')) AS name
                FROM respondent_case rc
                JOIN person p ON p.person_id = rc.person_id
                WHERE rc.blotter_case_id=%s
                ORDER BY name
            """, [case_id])
            resps = [r[0] for r in cur.fetchall()]

        out["complainant_name"] = ", ".join([x for x in cmps if x])
        out["respondent_name"]  = ", ".join([x for x in resps if x])

        print("[MED1-SETTLED][HEADER] =", json.dumps(out, ensure_ascii=False))
        return out

    # ---------------- public API ----------------------------------------------------------
    def build_name_value_map(self, form_id: int, submission_id: int) -> dict:
        # Determine the related case
        case_id = self._case_id_for_submission(submission_id)
        if not case_id:
            print("[MED1-SETTLED] ERROR: cannot resolve case_id for submission", submission_id)
            return {k: "" for k in _FIELDS}

        # Header (case details + parties)
        header = self._case_header(case_id)

        # Notices (KP-8/12) → first/second/third_notice_dt
        notices = self._notice_schedule_triplet(case_id)
        first_notice  = _format_dt(notices[0][0], notices[0][1]) if len(notices) >= 1 else ""
        second_notice = _format_dt(notices[1][0], notices[1][1]) if len(notices) >= 2 else ""
        third_notice  = _format_dt(notices[2][0], notices[2][1]) if len(notices) >= 3 else ""

        # Summons (KP-9) up to 3 + officer returns
        summons = self._summons_triplet(case_id)
        first_sum, second_sum, third_sum = summons[0], summons[1], summons[2]

        # KP-16 main + date
        main_text, settlement_dt = self._kp16_main_and_date(case_id)

        # 1st confrontation date/time = first KP-8/12 hearing_date
        first_conf_dt = _format_dt(notices[0][2], notices[0][3]) if len(notices) >= 1 else ""

        # Compose output defaults
        out = {
            # case
            "case_num": header["case_num"],
            "dt_filed": header["dt_filed"],
            "complaint_title": header["complaint_title"],
            "case_nature": header["case_nature"],
            "complainant_name": header["complainant_name"],
            "respondent_name": header["respondent_name"],

            # notices
            "first_notice_dt": first_notice,
            "second_notice_dt": second_notice,
            "third_notice_dt": third_notice,

            # summons
            "first_summon_dt":  first_sum.get("dt",""),
            "officer_return_dt": first_sum.get("offret",""),
            "second_summon_dt": second_sum.get("dt",""),
            "officer_return_dt2": second_sum.get("offret",""),
            "third_summon_dt":  third_sum.get("dt",""),
            "third_offret_dt":  third_sum.get("offret",""),

            # action taken
            "first_conf_dt": first_conf_dt,
            "settlement_dt": settlement_dt,

            # main point + misc
            "Text Box 1": main_text,
            "monitoring_remarks": "",
            "dt_exec": "",
            "dt_court_report": "",
            "dt_report_dilg": "",
            "monitoring_date": "",
        }

        # DUMMY mode: fill all with field names to confirm bindings
        if DUMMY_MODE:
            for k in _FIELDS:
                out[k] = k

        # Final debug dump (exact values we’re writing)
        try:
            print("[MED1-SETTLED] FINAL MAP:", json.dumps({k: out.get(k,"") for k in _FIELDS},
                                                         ensure_ascii=False, indent=2))
        except Exception:
            pass

        return out
