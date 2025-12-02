"""Fix the MaxLen property of the year field in barangay-residency.pdf"""
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, NumberObject

template_path = r"d:\CAPSTONE 2\cloned_repo\barug\pdf_templates\barangay-residency.pdf"
output_path = r"d:\CAPSTONE 2\cloned_repo\barug\pdf_templates\barangay-residency-fixed2.pdf"

reader = PdfReader(template_path)
writer = PdfWriter()
writer.clone_document_from_reader(reader)

# Find and fix the year field
for page in writer.pages:
    annots = page.get('/Annots')
    if annots:
        for annot_ref in annots:
            annot = annot_ref.get_object()
            if annot.get('/T') == 'year':
                print(f"Found year field!")
                print(f"  Current MaxLen: {annot.get('/MaxLen')}")
                print(f"  Current Rect: {annot.get('/Rect')}")
                
                # Remove the MaxLen restriction
                if '/MaxLen' in annot:
                    del annot[NameObject('/MaxLen')]
                    print(f"  Removed MaxLen restriction")
                
                print(f"  New MaxLen: {annot.get('/MaxLen')}")

with open(output_path, 'wb') as f:
    writer.write(f)

print(f"\nFixed PDF saved to: {output_path}")
