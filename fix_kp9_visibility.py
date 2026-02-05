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

def fix_kp9_visibility():
    with connection.cursor() as cursor:
        print("Making all KP9 fields visible...")
        
        # Set all KP9 fields to visible sort order (simple approach)
        cursor.execute("UPDATE kp_form_field SET sort_order = field_id * 10 WHERE form_id = 9")
        print(f"Updated KP9 field visibility: {cursor.rowcount} rows affected")
        
        # Verify the changes
        cursor.execute("""
            SELECT 
                kff.field_id,
                kff.sort_order,
                kff.label_override,
                f.base_label
            FROM kp_form_field kff
            JOIN kp_field f ON f.field_id = kff.field_id
            WHERE kff.form_id = 9
            ORDER BY kff.sort_order
            LIMIT 10
        """)
        
        print("\nFirst 10 visible KP9 fields:")
        for row in cursor.fetchall():
            print(f"  Field ID {row[0]}: {row[2] or row[3]} (sort_order: {row[1]})")

if __name__ == "__main__":
    fix_kp9_visibility()
    print("\nKP9 field visibility fix completed!")