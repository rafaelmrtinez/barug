"""
Script to automatically update Django templates to use cached bootstrap icons
Run with: python update_templates_to_cached_icons.py
"""
import os
import re
from pathlib import Path

# Base directory
BASE_DIR = Path(__file__).resolve().parent

# Template directories to scan
TEMPLATE_DIRS = [
    BASE_DIR / "lupon_mem" / "templates",
    BASE_DIR / "lupon_pres" / "templates",
    BASE_DIR / "secretary" / "templates",
    BASE_DIR / "clerk" / "templates",
    BASE_DIR / "templates",
]

def update_template_file(file_path):
    """Update a single template file to use cached icons"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        changes_made = False
        
        # Replace {% load bootstrap_icons %} with {% load cached_icons %}
        if '{% load bootstrap_icons %}' in content:
            content = content.replace('{% load bootstrap_icons %}', '{% load cached_icons %}')
            changes_made = True
        
        # Replace {% bs_icon with {% bs_icon_cached
        # Use regex to handle various spacing
        pattern = r'{%\s*bs_icon\s+'
        replacement = r'{% bs_icon_cached '
        if re.search(pattern, content):
            content = re.sub(pattern, replacement, content)
            changes_made = True
        
        # Only write if changes were made
        if changes_made and content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        
        return False
    
    except Exception as e:
        print(f"   ❌ Error processing {file_path}: {e}")
        return False

def scan_and_update_templates():
    """Scan all template directories and update files"""
    print("=" * 70)
    print("TEMPLATE ICON CACHE MIGRATION")
    print("=" * 70)
    print("\nScanning template directories for bootstrap icon usage...\n")
    
    total_files = 0
    updated_files = 0
    skipped_files = 0
    
    for template_dir in TEMPLATE_DIRS:
        if not template_dir.exists():
            print(f"⚠️  Directory not found: {template_dir}")
            continue
        
        print(f"\n📁 Scanning: {template_dir}")
        print("-" * 70)
        
        # Find all .html files
        html_files = list(template_dir.rglob("*.html"))
        
        for html_file in html_files:
            total_files += 1
            
            # Check if file uses bootstrap_icons
            try:
                with open(html_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                if '{% load bootstrap_icons %}' in content or '{% bs_icon' in content:
                    print(f"   📄 {html_file.relative_to(BASE_DIR)}")
                    
                    if update_template_file(html_file):
                        print(f"      ✅ Updated successfully")
                        updated_files += 1
                    else:
                        print(f"      ⚠️  No changes needed")
                        skipped_files += 1
            
            except Exception as e:
                print(f"   ❌ Error reading {html_file}: {e}")
    
    print("\n" + "=" * 70)
    print("MIGRATION SUMMARY")
    print("=" * 70)
    print(f"Total HTML files scanned:     {total_files}")
    print(f"Files updated:                {updated_files}")
    print(f"Files skipped (no changes):   {skipped_files}")
    print("=" * 70)
    
    if updated_files > 0:
        print("\n✅ Migration complete!")
        print("\nNext steps:")
        print("1. Review the changes with: git diff")
        print("2. Test the updated templates")
        print("3. Clear Django cache: python manage.py shell -c 'from django.core.cache import cache; cache.clear()'")
        print("4. Restart the Django server")
    else:
        print("\n⚠️  No files were updated. Templates may already be using cached icons.")

def create_backup():
    """Create a backup of templates before migration"""
    import shutil
    from datetime import datetime
    
    backup_dir = BASE_DIR / "template_backups" / datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n💾 Creating backup in: {backup_dir}")
    
    for template_dir in TEMPLATE_DIRS:
        if template_dir.exists():
            dest = backup_dir / template_dir.relative_to(BASE_DIR)
            shutil.copytree(template_dir, dest, dirs_exist_ok=True)
    
    print("✅ Backup created successfully\n")
    return backup_dir

if __name__ == "__main__":
    print("\n🚀 Starting template migration to cached bootstrap icons...\n")
    
    # Ask for confirmation
    response = input("This will modify template files. Create backup first? (y/n): ")
    if response.lower() == 'y':
        backup_dir = create_backup()
        print(f"Backup location: {backup_dir}\n")
    
    response = input("Proceed with migration? (y/n): ")
    if response.lower() != 'y':
        print("❌ Migration cancelled.")
        exit(0)
    
    scan_and_update_templates()
    
    print("\n" + "=" * 70)
    print("IMPORTANT: Test your templates after migration!")
    print("=" * 70)
