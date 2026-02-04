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

def make_kp8_fields_required():
    with connection.cursor() as cursor:
        print("Making KP8 'Made this:' and 'Notified this:' fields required...")
        
        # Make "Made this:" (field_id 42) required
        cursor.execute(
            "UPDATE kp_form_field SET is_required = true WHERE form_id = 8 AND field_id = 42"
        )
        print(f"Made 'Made this:' required: {cursor.rowcount} rows affected")
        
        # Make "Notified this:" (field_id 1121) required  
        cursor.execute(
            "UPDATE kp_form_field SET is_required = true WHERE form_id = 8 AND field_id = 1121"
        )
        print(f"Made 'Notified this:' required: {cursor.rowcount} rows affected")
        
        # Verify the changes
        cursor.execute("""
            SELECT 
                kff.field_id,
                kff.label_override,
                kff.is_required
            FROM kp_form_field kff
            WHERE kff.form_id = 8 AND kff.field_id IN (42, 1121)
            ORDER BY kff.field_id
        """)
        
        print("\nUpdated field requirements:")
        for row in cursor.fetchall():
            print(f"  Field ID {row[0]}: {row[1]} - Required: {row[2]}")

if __name__ == "__main__":
    make_kp8_fields_required()
    print("\nKP8 field requirements update completed!")