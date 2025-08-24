# resident/utils/pdf_forms.py
from io import BytesIO
from typing import Dict
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, BooleanObject  # <-- important

def fill_pdf_fields(pdf_path: str, data: Dict[str, str]) -> BytesIO:
    reader = PdfReader(str(pdf_path))
    writer = PdfWriter()

    # Copy pages
    for page in reader.pages:
        writer.add_page(page)

    # Copy AcroForm to the writer and set NeedAppearances properly
    root = reader.trailer["/Root"]
    if "/AcroForm" in root:
        acroform = root["/AcroForm"]
        # Use NameObject/BooleanObject, not raw strings/bools
        writer._root_object.update({NameObject("/AcroForm"): acroform})
        # Get the just-assigned AcroForm reference on the writer
        writer_acroform = writer._root_object[NameObject("/AcroForm")]
        writer_acroform.update({NameObject("/NeedAppearances"): BooleanObject(True)})

    # Fill the fields on page 0 (adjust if multi-page)
    writer.update_page_form_field_values(writer.pages[0], data)

    out = BytesIO()
    writer.write(out)
    out.seek(0)
    return out
