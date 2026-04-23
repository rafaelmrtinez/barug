"""Test that the year field accepts 4-digit years"""
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, BooleanObject
import io

from pathlib import Path
from pypdf import PdfReader

# folder where test_year_field.py lives (repo root: /home/runner/work/barug/barug)
BASE_DIR = Path(__file__).resolve().parent

# adjust this if pdf_templates is in a different folder
template_path = BASE_DIR / "pdf_templates" / "barangay-residency.pdf"

print("Using template:", template_path)

reader = PdfReader(str(template_path))
writer = PdfWriter()
writer.clone_document_from_reader(reader)

# Enable form field appearances
if "/AcroForm" in writer._root_object:
    writer._root_object["/AcroForm"].update({
        NameObject("/NeedAppearances"): BooleanObject(True)
    })

# Fill the year field
test_values = {
    "year": "2025",
    "date": "02",
    "month": "December"
}

for page in writer.pages:
    writer.update_page_form_field_values(page, test_values)

# Write to buffer
buf = io.BytesIO()
writer.write(buf)
pdf_bytes = buf.getvalue()

print(f"[OK] Successfully created PDF with year='2025'")
print(f"     PDF size: {len(pdf_bytes)} bytes")

# Save test PDF
with open("test_year_output.pdf", "wb") as f:
    f.write(pdf_bytes)

print(f"[OK] Test PDF saved as: test_year_output.pdf")
print(f"\nPlease open test_year_output.pdf and verify:")
print(f"  - Year field shows '2025' (not '2')")
print(f"  - Date field shows '02'")
print(f"  - Month field shows 'December'")
