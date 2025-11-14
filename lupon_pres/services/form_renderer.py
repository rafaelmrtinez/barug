# lupon_pres/services/form_renderer.py
"""
Minimal form renderer for lupon_pres
"""
from typing import Tuple

def render_preview_png(submission_id: int) -> bytes:
    """Render form preview as PNG"""
    return b""

def render_final_pdf(submission_id: int) -> Tuple[bytes, str]:
    """Render final PDF"""
    return b"", f"form_{submission_id}.pdf"