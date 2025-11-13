#!/usr/bin/env python3
"""
Script to add notification calls to all KP forms (KP-13 through KP-25)
"""

import os
import re

# KP forms and their notification function names
KP_FORMS = {
    13: "notify_kp13_arbitration_award",
    14: "notify_kp14_certificate_to_file_action", 
    15: "notify_kp15_execution_settlement",
    16: "notify_kp16_repudiation_settlement",
    17: "notify_kp17_complaint_criminal",
    18: "notify_kp18_subpoena",
    19: "notify_kp19_contempt_citation",
    20: "notify_kp20_monthly_report",
    21: "notify_kp21_quarterly_report",
    22: "notify_kp22_annual_report",
    23: "notify_kp23_case_record",
    24: "notify_kp24_notice_final_settlement",
    25: "notify_kp25_case_closure"
}

def add_notification_to_kp_file(kp_num, file_path):
    """Add notification call to a KP form file"""
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check if notifications already added
    if "notifications.views import" in content:
        print(f"KP-{kp_num} already has notifications")
        return
    
    notification_func = KP_FORMS[kp_num]
    
    # Find the return statement at the end of build_name_value_map
    pattern = r'(\s+)(return out)(\s*)$'
    
    notification_code = f"""        # ---------------------------------------------------
        # Send notifications for KP-{kp_num} submission
        # ---------------------------------------------------
        try:
            from notifications.views import {notification_func}
            with connection.cursor() as cur:
                cur.execute(
                    "SELECT blotter_case_id FROM blotter_kp_submission WHERE submission_id=%s",
                    [submission_id]
                )
                row = cur.fetchone()
                if row:
                    case_id = row[0]
                    # Get case number from DB
                    cur.execute("SELECT blotter_case_num FROM blotter_case WHERE blotter_case_id=%s", [case_id])
                    case_row = cur.fetchone()
                    case_num = case_row[0] if case_row else ""
                    {notification_func}(case_id, case_num)
        except Exception as e:
            logger.warning("[KP{kp_num}] Failed to send notifications: %s", e)

        \\2"""
    
    # Replace the return statement
    new_content = re.sub(pattern, notification_code, content, flags=re.MULTILINE)
    
    if new_content != content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Added notifications to KP-{kp_num}")
    else:
        print(f"Could not find return statement in KP-{kp_num}")

def main():
    base_path = "lupon_mem/services/forms"
    
    for kp_num in KP_FORMS.keys():
        file_path = f"{base_path}/kp{kp_num}.py"
        add_notification_to_kp_file(kp_num, file_path)
    
    # Handle special cases
    special_files = ["kp20a.py", "kp20b.py", "kp9_2.py"]
    for special_file in special_files:
        file_path = f"{base_path}/{special_file}"
        if os.path.exists(file_path):
            kp_num = special_file.replace(".py", "").replace("kp", "")
            print(f"Special file found: {special_file} - manual review needed")

if __name__ == "__main__":
    main()