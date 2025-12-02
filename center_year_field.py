"""Center align the year field in barangay-residency.pdf"""
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, NumberObject

template_path = r"d:\CAPSTONE 2\cloned_repo\barug\pdf_templates\barangay-residency.pdf"
output_path = r"d:\CAPSTONE 2\cloned_repo\barug\pdf_templates\barangay-residency-centered.pdf"

reader = PdfReader(template_path)
writer = PdfWriter()
writer.clone_document_from_reader(reader)

# Find and center the year field
for page in writer.pages:
    annots = page.get('/Annots')
    if annots:
        for annot_ref in annots:
            annot = annot_ref.get_object()
            if annot.get('/T') == 'year':
                print(f"Found year field!")
                print(f"  Current Q (alignment): {annot.get('/Q')}")
                
                # Set Q to 1 for center alignment (0=left, 1=center, 2=right)
                annot[NameObject('/Q')] = NumberObject(1)
                
                print(f"  New Q (alignment): {annot.get('/Q')} (center)")

with open(output_path, 'wb') as f:
    writer.write(f)

print(f"\nFixed PDF saved to: {output_path}")
