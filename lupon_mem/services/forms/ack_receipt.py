# lupon_mem/services/forms/ack_receipt.py
from __future__ import annotations
from typing import Dict, Set
from datetime import datetime as _dt
from zoneinfo import ZoneInfo
import json, logging
from django.db import connection
from .. import form_shared as FS

logger = logging.getLogger(__name__)

_FIELDS = [
    "date","payee_name","amount_in_words","amount_in_num",
    "total_amount","total_amnt_in_words","month_of","payee_name_2",
]
_SOURCES: Dict[str, Set[str]] = {
    "date": {"date","dt","date_today","current_date"},
    "payee_name": {"payee_name","payee","recipient","name"},
    "amount_in_words": {"amount_in_words","amount_words"},
    "amount_in_num": {"amount_in_num","amount_numeric","amount"},
    "total_amount": {"total_amount"},
    "total_amnt_in_words": {"total_amnt_in_words","total_amount_in_words"},
    "month_of": {"month_of","month"},
    "payee_name_2": {"payee_name_2","payee_two"},
}

def _today_ph(fmt="%B %d, %Y"): return _dt.now(ZoneInfo("Asia/Manila")).strftime(fmt)

class AckReceiptHandler:
    def _log(self, out: Dict[str, str]):
        try:
            ordered = {k: out.get(k,"") for k in _FIELDS}
            print("[ACK-RECEIPT] fill map:\n", json.dumps(ordered, ensure_ascii=False, indent=2))
            logger.info("ACK-RECEIPT fill map:\n%s", json.dumps(ordered, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.warning("ACK-RECEIPT logging failed: %s", e)

    def build_name_value_map(self, form_id: int, submission_id: int) -> dict:
        answers = FS.load_answers(submission_id)
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
        by_label, by_code = {}, {}
        for fid,label,code in rows:
            val = answers.get(str(fid))
            if isinstance(val,str): val = FS.sanitize_text(val)
            if val not in (None,"","null"):
                if label: by_label[label.strip().lower()] = val
                if code:  by_code[code.strip().lower()]  = val

        def get(keys:Set[str])->str:
            for k in keys:
                kk = k.strip().lower()
                if kk in by_label: return FS.normalize(by_label[kk])
                if kk in by_code:  return FS.normalize(by_code[kk])
            return ""

        out: Dict[str,str] = {t:get(srcs) for t,srcs in _SOURCES.items()}
        if not out.get("date"): out["date"] = _today_ph()
        if not out.get("month_of"): out["month_of"] = _today_ph("%B")

        for k,v in list(out.items()):
            if isinstance(v,str): out[k]=FS.sanitize_text(v)
        for k in _FIELDS: out.setdefault(k,"")
        self._log(out)
        return out
