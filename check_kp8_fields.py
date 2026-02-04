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

def check_and_fix_kp8_fields():
    with connection.cursor() as cursor:
        print("Checking current KP8 form field visibility...")
        
        # Check all KP8 fields
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
            WHERE kff.form_id = 8
            ORDER BY kff.sort_order, kff.kp_form_field_id
        """)
        
        print("\nAll KP8 fields:")
        all_fields = cursor.fetchall()
        for row in all_fields:
            print(f"  Field ID {row[2]}: {row[5] or row[6]} (sort_order: {row[3]}, code: {row[7]})")
        
        # Reset and fix the visibility
        print("\nFixing KP8 field visibility...")
        
        # First, hide all fields
        cursor.execute("UPDATE kp_form_field SET sort_order = 9999 WHERE form_id = 8")
        print(f"Hidden all KP8 fields: {cursor.rowcount} rows affected")
        
        # Show the 6 required fields
        required_fields = [
            (10, 1),    # Complainant(s)
            (20, 2),    # Respondent(s)
            (30, 12),   # Hearing Date
            (40, 13),   # Hearing Time
            (50, 42),   # Made this:
            (60, 1121)  # Notified this:
        ]
        
        for sort_order, field_id in required_fields:
            cursor.execute(
                "UPDATE kp_form_field SET sort_order = %s WHERE form_id = 8 AND field_id = %s",
                [sort_order, field_id]
            )
            print(f"Updated field_id {field_id} to sort_order {sort_order}: {cursor.rowcount} rows affected")
        
        # Verify the final state
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
            WHERE kff.form_id = 8 AND kff.sort_order < 9999
            ORDER BY kff.sort_order, kff.kp_form_field_id
        """)
        
        print("\nVisible KP8 fields after fix:")
        visible_fields = cursor.fetchall()
        for row in visible_fields:
            print(f"  Field ID {row[2]}: {row[5] or row[6]} (sort_order: {row[3]}, code: {row[7]})")
        
        if len(visible_fields) != 6:
            print(f"\nWARNING: Expected 6 visible fields, but found {len(visible_fields)}")
            
            # Check if the fields exist at all
            missing_field_ids = [1, 2, 12, 13, 42, 1121]
            for field_id in missing_field_ids:
                cursor.execute(
                    "SELECT COUNT(*) FROM kp_form_field WHERE form_id = 8 AND field_id = %s",
                    [field_id]
                )
                count = cursor.fetchone()[0]
                if count == 0:
                    print(f"  Field ID {field_id} does not exist in kp_form_field for form_id=8")

if __name__ == "__main__":
    check_and_fix_kp8_fields()
    print("\nKP8 field check and fix completed!")