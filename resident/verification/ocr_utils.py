# resident/verification/ocr_utils.py
import re
from typing import Optional, Tuple, Dict
import pytesseract
from PIL import Image, ImageOps, UnidentifiedImageError
from .constants import DOCUMENT_KEYWORDS

# If on Windows and tesseract isn't in PATH, set the full path:
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

def _normalize(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _preprocess_for_ocr(img: Image.Image) -> Image.Image:
    try:
        img = ImageOps.exif_transpose(img)  # fix rotation
    except Exception:
        pass
    g = ImageOps.grayscale(img)
    g = ImageOps.autocontrast(g)
    if min(g.size) < 900:
        scale = 900 / float(min(g.size))
        g = g.resize((int(g.width * scale), int(g.height * scale)))
    return g

def extract_text_from_file(file_obj) -> str:
    """
    Open the image, run OCR, and then rewind the file object so callers
    can reuse the stream (e.g., for upload).
    """
    try:
        img = Image.open(file_obj)
    except UnidentifiedImageError:
        try:
            file_obj.seek(0)
        except Exception:
            pass
        return ""
    img = _preprocess_for_ocr(img)
    text = pytesseract.image_to_string(img, lang="eng", config="--oem 3 --psm 6")

    # Rewind so subsequent code (uploads) can read from the start
    try:
        file_obj.seek(0)
    except Exception:
        pass
    return text or ""

def is_document_type_valid(ocr_text: str, doc_type_key: str) -> bool:
    ocr_norm = _normalize(ocr_text)
    keywords = DOCUMENT_KEYWORDS.get(doc_type_key, [])
    if not keywords:
        return False
    hits = 0
    for kw in keywords:
        kw_norm = _normalize(kw)
        if kw_norm and kw_norm in ocr_norm:
            hits += 1
    # require all if <= 2 keywords; else at least 2 hits
    return hits >= (len(keywords) if len(keywords) <= 2 else 2)

def _tokenize_name_part(s: str):
    # split multi-word names; keep tokens length>=2 to avoid noise
    return [t for t in _normalize(s).split() if len(t) >= 2]

def _any_token_found(haystack_norm: str, tokens) -> bool:
    return any(t in haystack_norm for t in tokens)

def is_name_match_loose(
    ocr_text: str,
    first_name: str,
    last_name: str,
    middle_name: str = ""
) -> Tuple[bool, Dict[str, bool]]:
    """
    Loose rule:
      - Pass if LAST name appears AND (FIRST or MIDDLE) appears anywhere.
      - Middle is optional but recorded if matched.
      - Multi-word names pass if any token matches (helps with OCR splits).
    Returns (ok, hits_dict)
    """
    o = _normalize(ocr_text)

    first_tokens  = _tokenize_name_part(first_name or "")
    last_tokens   = _tokenize_name_part(last_name or "")
    middle_tokens = _tokenize_name_part(middle_name or "")

    if not last_tokens:
        return False, {"first": False, "middle": False, "last": False}

    first_hit  = _any_token_found(o, first_tokens) if first_tokens else False
    last_hit   = _any_token_found(o, last_tokens)
    middle_hit = _any_token_found(o, middle_tokens) if middle_tokens else False

    ok = last_hit and (first_hit or middle_hit)
    return ok, {"first": first_hit, "middle": middle_hit, "last": last_hit}

def validate_doc_from_images(
    front_file,
    back_file,
    doc_type_key: str,
    name_tuple: Optional[Tuple[str, str, str]] = None,  # (first, last, middle)
) -> dict:
    """
    Returns:
      {
        "ok": bool,
        "doc_type_ok": bool,
        "name_ok": Optional[bool],
        "name_hits": Optional[{'first': bool, 'middle': bool, 'last': bool}],
        "text_front": str,
        "text_back": str,
        "which_matched": "front" | "back",
        "reason": str
      }
    """
    text_front = extract_text_from_file(front_file) if front_file else ""
    text_back  = extract_text_from_file(back_file)  if back_file  else ""

    primary = text_front if len(text_front) >= len(text_back) else text_back
    combined = (text_front + " " + text_back).strip()
    corpus = primary or combined

    doc_type_ok = is_document_type_valid(corpus, doc_type_key)

    name_ok = None
    name_hits = None
    if name_tuple:
        f, l, m = name_tuple
        name_ok, name_hits = is_name_match_loose(corpus, f, l, m)

    ok = doc_type_ok if name_ok is None else (doc_type_ok and bool(name_ok))
    reason = ""
    if not doc_type_ok:
        reason = "Document text does not match expected ID type."
    elif name_ok is False:
        if name_hits:
            missing = []
            if not name_hits.get("last"):
                missing.append("last name")
            if not (name_hits.get("first") or name_hits.get("middle")):
                missing.append("first or middle name")
            reason = "Name not fully detected: " + ", ".join(missing)
        else:
            reason = "Name not detected on the ID."

    return {
        "ok": ok,
        "doc_type_ok": doc_type_ok,
        "name_ok": name_ok,
        "name_hits": name_hits,
        "text_front": text_front,
        "text_back": text_back,
        "which_matched": "front" if len(text_front) >= len(text_back) else "back",
        "reason": reason,
    }
