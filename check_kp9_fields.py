#!/usr/bin/env python
import os
import sys
import django

# Add the project directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'barug.settings')
django.setup()

from django.db import connection

def check_kp9_fields():
    with connection.cursor() as cursor:
        print("Checking KP9 form field visibility...")
        
        # Check all KP9 fields
        cursor.execute("""
            SELECT 
                kff.kp_form_field_id,
                kff.form_id,
                kff.field_id,
                kff.sort_order,
                kff.is_required,
                kff.label_override,
                f.base_label,
                f.field_code
            FROM kp_form_field kff
            JOIN kp_field f ON f.field_id = kff.field_id
            WHERE kff.form_id = 9
            ORDER BY kff.sort_order, kff.kp_form_field_id
        """)
        
        print("\nAll KP9 fields:")
        all_fields = cursor.fetchall()
        if not all_fields:
            print("  No fields found for form_id = 9")
        else:
            for row in all_fields:
                print(f"  Field ID {row[2]}: {row[5] or row[6]} (sort_order: {row[3]}, code: {row[7]})")
        
        # Check if form exists
        cursor.execute("SELECT form_id, form_code, form_name FROM kp_form WHERE form_id = 9")
        form_info = cursor.fetchone()
        if form_info:
            print(f"\nForm info: ID={form_info[0]}, Code={form_info[1]}, Name={form_info[2]}")
        else:
            print("\nForm ID 9 does not exist in kp_form table")

if __name__ == "__main__":
    check_kp9_fields()
    print("\nKP9 field check completed!")