#!/usr/bin/env python3
"""
Simple test script to verify heatmap database functions work correctly.
Run this from the Django project root: python test_heatmap.py
"""

import os
import sys
import django
from datetime import datetime, timedelta

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'src.settings')
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
django.setup()

from django.db import connection

def test_heatmap_functions():
    """Test the heatmap database functions"""
    print("Testing heatmap database functions...")
    
    with connection.cursor() as cur:
        # Test fn_heatmap_points
        print("\n1. Testing fn_heatmap_points...")
        try:
            cur.execute("SELECT * FROM fn_heatmap_points(NULL, NULL, NULL) LIMIT 5")
            points = cur.fetchall()
            print(f"   ✓ Found {len(points)} sample points")
            if points:
                columns = [desc[0] for desc in cur.description]
                print(f"   ✓ Columns: {', '.join(columns)}")
        except Exception as e:
            print(f"   ✗ Error: {e}")
        
        # Test fn_heatmap_bins
        print("\n2. Testing fn_heatmap_bins...")
        try:
            cur.execute("SELECT * FROM fn_heatmap_bins(NULL, NULL, 3) LIMIT 5")
            bins = cur.fetchall()
            print(f"   ✓ Found {len(bins)} density bins")
            if bins:
                columns = [desc[0] for desc in cur.description]
                print(f"   ✓ Columns: {', '.join(columns)}")
        except Exception as e:
            print(f"   ✗ Error: {e}")
        
        # Test fn_heatmap_time_of_week
        print("\n3. Testing fn_heatmap_time_of_week...")
        try:
            cur.execute("SELECT * FROM fn_heatmap_time_of_week(NULL, NULL) LIMIT 10")
            time_data = cur.fetchall()
            print(f"   ✓ Found {len(time_data)} time patterns")
            if time_data:
                columns = [desc[0] for desc in cur.description]
                print(f"   ✓ Columns: {', '.join(columns)}")
        except Exception as e:
            print(f"   ✗ Error: {e}")
        
        # Test basic statistics
        print("\n4. Testing basic statistics...")
        try:
            cur.execute("""
                SELECT 
                    COUNT(*) as total_reports,
                    COUNT(CASE WHEN a.latitude IS NOT NULL AND a.longitude IS NOT NULL THEN 1 END) as mapped_reports
                FROM blotter_report br
                LEFT JOIN addresss a ON a.address_id = br.incident_address_id
                WHERE br.date_time_reported >= CURRENT_DATE - INTERVAL '12 months'
            """)
            stats = cur.fetchone()
            print(f"   ✓ Total reports (last 12 months): {stats[0]}")
            print(f"   ✓ Mapped reports: {stats[1]}")
        except Exception as e:
            print(f"   ✗ Error: {e}")
        
        # Test case natures
        print("\n5. Testing case natures...")
        try:
            cur.execute("SELECT case_nature_id, case_name FROM case_nature ORDER BY case_name LIMIT 5")
            natures = cur.fetchall()
            print(f"   ✓ Found {len(natures)} case nature types")
            for nature in natures:
                print(f"      - {nature[1]} (ID: {nature[0]})")
        except Exception as e:
            print(f"   ✗ Error: {e}")

def test_with_date_filters():
    """Test functions with date filters"""
    print("\n\nTesting with date filters...")
    
    # Test with last 30 days
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=30)
    
    with connection.cursor() as cur:
        try:
            cur.execute("SELECT * FROM fn_heatmap_points(%s, %s, NULL)", [start_date, end_date])
            points = cur.fetchall()
            print(f"   ✓ Points in last 30 days: {len(points)}")
            
            cur.execute("SELECT * FROM fn_heatmap_bins(%s, %s, 4)", [start_date, end_date])
            bins = cur.fetchall()
            print(f"   ✓ Density bins in last 30 days: {len(bins)}")
            
        except Exception as e:
            print(f"   ✗ Error with date filters: {e}")

if __name__ == "__main__":
    print("=" * 50)
    print("BARANGAY INCIDENT HEATMAP TEST")
    print("=" * 50)
    
    test_heatmap_functions()
    test_with_date_filters()
    
    print("\n" + "=" * 50)
    print("Test completed!")
    print("If all tests passed, your heatmap should work correctly.")
    print("=" * 50)