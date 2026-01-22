"""
PDF Form Field Inspector
This script extracts and displays all form field names from a PDF file.
"""

import PyPDF2
import sys

def get_pdf_fields(pdf_path):
    """Extract all form field names from a PDF file."""
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            
            # Check if PDF has form fields
            if '/AcroForm' in pdf_reader.trailer['/Root']:
                fields = pdf_reader.get_fields()
                
                if fields:
                    print(f"\n{'='*60}")
                    print(f"PDF FORM FIELDS FOUND: {len(fields)}")
                    print(f"{'='*60}\n")
                    
                    for field_name, field_info in fields.items():
                        field_type = field_info.get('/FT', 'Unknown')
                        field_value = field_info.get('/V', '')
                        
                        print(f"Field Name: {field_name}")
                        print(f"  Type: {field_type}")
                        print(f"  Current Value: {field_value}")
                        print(f"  Full Info: {field_info}")
                        print("-" * 60)
                else:
                    print("\nNo form fields found in this PDF.")
            else:
                print("\nThis PDF does not contain an AcroForm (no fillable fields).")
                
    except FileNotFoundError:
        print(f"Error: File not found - {pdf_path}")
    except Exception as e:
        print(f"Error reading PDF: {str(e)}")

if __name__ == "__main__":
    # Default path
    pdf_path = r"d:\CAPSTONE 2\cloned_repo\barug\static\kp_forms\lupon_blotter_file.pdf"
    
    # Allow command line argument
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
    
    print(f"Inspecting PDF: {pdf_path}\n")
    get_pdf_fields(pdf_path)
