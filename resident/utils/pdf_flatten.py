from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from pypdf import PdfReader, PdfWriter

# map where each field should be drawn on the page (adjust once; mm from bottom-left)
FIELD_POS = {
    "recipient":  (40*mm, 165*mm, 12),   # (x, y, font_size)
    "requestor":  (40*mm, 140*mm, 11),
    "application":(40*mm, 132*mm, 11),
    "date":       (40*mm, 120*mm, 11),
    "month_year": (160*mm, 15*mm, 10),
}

def flatten_filled_pdf(filled_pdf: BytesIO, data: dict, page_size=letter) -> BytesIO:
    # 1) build overlay
    overlay = BytesIO()
    c = canvas.Canvas(overlay, pagesize=page_size)

    for key, (x, y, size) in FIELD_POS.items():
        val = str(data.get(key, "")).strip()
        if not val:
            continue
        c.setFont("Helvetica-Bold" if key in ("recipient", "application") else "Helvetica", size)
        # right align month_year; others left
        if key == "month_year":
            w = c.stringWidth(val)
            c.drawString(x - w, y, val)
        else:
            c.drawString(x, y, val)

    c.save()
    overlay.seek(0)

    # 2) merge overlay onto the already-filled PDF
    base = PdfReader(filled_pdf)
    over = PdfReader(overlay)
    out = PdfWriter()

    for i, page in enumerate(base.pages):
        page.merge_page(over.pages[0])  # one-page overlay
        out.add_page(page)

    result = BytesIO()
    out.write(result)
    result.seek(0)
    return result
