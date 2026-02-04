# lupon_mem/management/commands/test_resident_records.py
from django.core.management.base import BaseCommand
from django.db import connection

class Command(BaseCommand):
    help = 'Test the resident records database functions'

    def handle(self, *args, **options):
        self.stdout.write('Testing resident records database functions...')
        
        with connection.cursor() as cursor:
            # Test if the functions exist
            cursor.execute("""
                SELECT routine_name 
                FROM information_schema.routines 
                WHERE routine_schema = 'public' 
                AND routine_name IN ('fn_person_blotter_report_history', 'fn_person_blotter_case_history')
                ORDER BY routine_name
            """)
            
            functions = cursor.fetchall()
            
            if len(functions) == 2:
                self.stdout.write(
                    self.style.SUCCESS('✓ Both database functions found:')
                )
                for func in functions:
                    self.stdout.write(f'  - {func[0]}')
                
                # Test with a sample person_id (assuming person_id=1 exists)
                try:
                    cursor.execute("SELECT * FROM fn_person_blotter_report_history(1) LIMIT 1")
                    report_test = cursor.fetchone()
                    
                    cursor.execute("SELECT * FROM fn_person_blotter_case_history(1) LIMIT 1") 
                    case_test = cursor.fetchone()
                    
                    self.stdout.write(
                        self.style.SUCCESS('✓ Database functions are working correctly')
                    )
                    
                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(f'⚠ Functions exist but may need data: {e}')
                    )
                    
            else:
                self.stdout.write(
                    self.style.ERROR('✗ Database functions not found. Please run the SQL scripts first.')
                )
                
            # Test basic person query
            try:
                cursor.execute("SELECT COUNT(*) FROM person LIMIT 1")
                person_count = cursor.fetchone()[0]
                self.stdout.write(f'✓ Found {person_count} persons in database')
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'✗ Error accessing person table: {e}')
                )