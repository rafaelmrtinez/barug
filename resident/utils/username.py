import re
from datetime import datetime, date

_USERNAME_SUFFIX_DOMAIN = "@user"

def _slug_module(s: str | None) -> str:
    if s is None:
        return ""
    return re.sub(r'[^a-z0-9]+', '', str(s).strip().lower())

def _first_initials(first_name: str | None) -> str:
    if not first_name:
        return ""
    tokens = re.findall(r"[A-Za-z0-9]+", str(first_name))
    if not tokens:
        return ""
    initials = "".join(t[0] for t in tokens)
    return _slug_module(initials)

def _mmddyy_from_input(dob_raw) -> str | None:
    if not dob_raw:
        return None
    dt = None
    if isinstance(dob_raw, datetime):
        dt = dob_raw.date()
    elif isinstance(dob_raw, date):
        dt = dob_raw
    else:
        val = str(dob_raw).strip()
        fmts = [
            "%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%Y/%m/%d",
            "%d-%m-%Y", "%d/%m/%Y",
            "%m/%d/%y", "%m-%d-%y", "%d-%m-%y", "%d/%m/%y",
            "%Y%m%d", "%m%d%Y"
        ]
        for f in fmts:
            try:
                dt = datetime.strptime(val, f).date()
                break
            except ValueError:
                continue
        if dt is None:
            digits = re.sub(r"\D+", "", val)
            if len(digits) == 8:
                try:
                    dt = datetime.strptime(digits, "%Y%m%d").date()
                except ValueError:
                    dt = datetime.strptime(digits, "%m%d%Y").date()
    return dt.strftime("%m%d%y") if dt else None

def generate_username(first_name: str | None, last_name: str | None, dob_raw) -> str:
    fi = _first_initials(first_name)
    ln_raw = _slug_module(last_name)
    mmddyy = _mmddyy_from_input(dob_raw) or "000000"

    if ln_raw:
        base = f"{fi or 'u'}{ln_raw}"
    else:
        base = fi or "user"

    return f"{base}.{mmddyy}{_USERNAME_SUFFIX_DOMAIN}"[:150]
