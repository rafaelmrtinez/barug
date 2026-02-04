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

def update_kp8_fields():
    with connection.cursor() as cursor:
        print("Updating KP8 form field visibility...")
        
        # Hide all KP8 form fields first
        cursor.execute("UPDATE kp_form_field SET sort_order = 9999 WHERE form_id = 8")
        print(f"Hidden all KP8 fields: {cursor.rowcount} rows affected")
        
        # Show only the 6 required fields with proper sort order
        updates = [
            (10, 1, "Complainant(s)"),
            (20, 2, "Respondent(s)"),
            (30, 12, "Hearing Date"),
            (40, 13, "Hearing Time"),
            (50, 42, "Made this:"),
            (60, 1121, "Notified this:")
        ]
        
        for sort_order, field_id, label in updates:
            cursor.execute(
                "UPDATE kp_form_field SET sort_order = %s WHERE form_id = 8 AND field_id = %s",
                [sort_order, field_id]
            )
            print(f"Updated {label} (field_id={field_id}): {cursor.rowcount} rows affected")
        
        # Verify the changes
        cursor.execute("""
            SELECT 
                kff.kp_form_field_id,
                kff.form_id,
                kff.field_id,
                kff.sort_order,
                kff.is_required,
                kff.label_override,
                f.base_label
            FROM kp_form_field kff
            JOIN kp_field f ON f.field_id = kff.field_id
            WHERE kff.form_id = 8 AND kff.sort_order < 9999
            ORDER BY kff.sort_order, kff.kp_form_field_id
        """)
        
        print("\nVisible KP8 fields after update:")
        for row in cursor.fetchall():
            print(f"  Field ID {row[2]}: {row[5] or row[6]} (sort_order: {row[3]})")

if __name__ == "__main__":
    update_kp8_fields()
    print("\nKP8 field visibility update completed!")