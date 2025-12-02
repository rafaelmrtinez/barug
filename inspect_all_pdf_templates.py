"""
Script to inspect all PDF templates and identify potential field width issues
"""
from pypdf import PdfReader
import os
from pathlib import Path

def inspect_pdf_fields(pdf_path):
    """Inspect all fields in a PDF and return field information"""
    try:
        reader = PdfReader(pdf_path)
        fields = reader.get_fields()
        
        if not fields:
            return None
        
        field_info = []
        for page in reader.pages:
            annots = page.get('/Annots')
            if not annots:
                continue
            
            for annot_ref in annots:
                annot = annot_ref.get_object()
                if annot.get('/Subtype') == '/Widget':
                    field_name = str(annot.get('/T', '')).strip('()')
                    rect = annot.get('/Rect')
                    
                    if rect and field_name:
                        width = float(rect[2]) - float(rect[0])
                        height = float(rect[3]) - float(rect[1])
                        
                        # Flag potentially problematic fields
                        issues = []
                        if width < 40 and ('year' in field_name.lower() or 'date' in field_name.lower()):
                            issues.append(f"[!] Width too narrow for date/year field ({width:.1f} units)")
                        if width < 30:
                            issues.append(f"[!] Very narrow field ({width:.1f} units)")
                        if height < 10:
                            issues.append(f"[!] Very short field ({height:.1f} units)")
                        
                        field_info.append({
                            'name': field_name,
                            'width': width,
                            'height': height,
                            'rect': [float(r) for r in rect],
                            'issues': issues
                        })
        
        return field_info
    except Exception as e:
        return {'error': str(e)}

def main():
    templates_dir = Path(r"d:\CAPSTONE 2\cloned_repo\barug\pdf_templates")
    
    print("=" * 80)
    print("PDF TEMPLATE FIELD INSPECTION REPORT")
    print("=" * 80)
    print()
    
    pdf_files = list(templates_dir.glob("*.pdf"))
    
    for pdf_file in sorted(pdf_files):
        if 'backup' in pdf_file.name.lower() or 'fixed' in pdf_file.name.lower():
            continue
        
        print(f"\n[PDF] {pdf_file.name}")
        print("-" * 80)
        
        field_info = inspect_pdf_fields(str(pdf_file))
        
        if field_info is None:
            print("   No form fields found")
            continue
        
        if isinstance(field_info, dict) and 'error' in field_info:
            print(f"   [X] Error: {field_info['error']}")
            continue
        
        # Group fields by issues
        fields_with_issues = [f for f in field_info if f['issues']]
        fields_ok = [f for f in field_info if not f['issues']]
        
        if fields_with_issues:
            print(f"\n   [!] FIELDS WITH POTENTIAL ISSUES ({len(fields_with_issues)}):")
            for field in fields_with_issues:
                print(f"\n      Field: {field['name']}")
                print(f"      Size: {field['width']:.1f} x {field['height']:.1f} units")
                print(f"      Rect: {field['rect']}")
                for issue in field['issues']:
                    print(f"      {issue}")
        
        if fields_ok:
            print(f"\n   [OK] FIELDS OK ({len(fields_ok)}):")
            for field in fields_ok:
                print(f"      {field['name']}: {field['width']:.1f} x {field['height']:.1f} units")
    
    print("\n" + "=" * 80)
    print("INSPECTION COMPLETE")
    print("=" * 80)
    print("\nRecommendations:")
    print("1. Fields with width < 40 units may have display issues for long text")
    print("2. Year fields should be at least 50 units wide for 4-digit years")
    print("3. Date fields should be at least 60 units wide for full dates")
    print("4. Consider using the fix_pdf_year_field.py script as a template to fix issues")

if __name__ == "__main__":
    main()
