"""Test that the year field accepts 4-digit years"""
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, BooleanObject
import io

template_path = r"d:\CAPSTONE 2\cloned_repo\barug\pdf_templates\barangay-residency.pdf"

# Test filling the year field with "2025"
reader = PdfReader(template_path)
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
