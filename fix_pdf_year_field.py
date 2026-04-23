"""
Script to inspect and fix the year field in the barangay-residency.pdf template
"""
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, NumberObject
import os

template_path = r"d:\CAPSTONE 2\cloned_repo\barug\pdf_templates\barangay-residency.pdf"
output_path = r"d:\CAPSTONE 2\cloned_repo\barug\pdf_templates\barangay-residency-fixed.pdf"

reader = PdfReader(template_path)
writer = PdfWriter()

# Clone the document
writer.clone_document_from_reader(reader)

# Get the form fields
fields = reader.get_fields()

if fields:
    print("Current fields:")
    for field_name, field_obj in fields.items():
        print(f"  {field_name}:")
        print(f"    Type: {field_obj.get('/FT')}")
        print(f"    MaxLen: {field_obj.get('/MaxLen')}")
        print(f"    Rect: {field_obj.get('/Rect')}")
        
        # If this is the year field, try to expand it
        if field_name == 'year':
            print(f"    Found year field!")
            # Get the annotation object
            for page in writer.pages:
                annots = page.get('/Annots')
                if annots:
                    for annot_ref in annots:
                        annot = annot_ref.get_object()
                        if annot.get('/T') == 'year':
                            print(f"    Modifying year field...")
                            # Get current rect
                            rect = annot.get('/Rect')
                            if rect:
                                print(f"    Current rect: {rect}")
                                # Expand the width of the field
                                # rect format: [x1, y1, x2, y2]
                                from pypdf.generic import ArrayObject, FloatObject
                                new_rect = ArrayObject([
                                    FloatObject(rect[0]),
                                    FloatObject(rect[1]),
                                    FloatObject(rect[2] + 30),  # Expand width by 30 units
                                    FloatObject(rect[3])
                                ])
                                annot[NameObject('/Rect')] = new_rect
                                print(f"    New rect: {new_rect}")

# Save the modified PDF
with open(output_path, 'wb') as f:
    writer.write(f)

print(f"\nFixed PDF saved to: {output_path}")
print("Please review the fixed PDF and replace the original if it looks correct.")
