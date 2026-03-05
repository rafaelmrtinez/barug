import re

# Read the file
with open(r'c:\Users\panch\OneDrive\BaRUG v3 Jan 31\barug-for_lupon_updated\lupon_mem\templates\lupon_mem\form_builder.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace all occurrences for kp9_ui_minimal
content = content.replace(
    "{% if kp9_ui_minimal and code != 'curr_date' and code != 'recipient_address' %} kp-offscreen{% endif %}",
    "{% if kp9_ui_minimal and code != 'curr_date' and code != 'recipient_address' and field_id != 1143 %} kp-offscreen{% endif %}"
)

# Replace all occurrences for kp12_ui_minimal
content = content.replace(
    "{% if kp12_ui_minimal and code != 'date_created' and code != 'time_created' %} kp-offscreen{% endif %}",
    "{% if kp12_ui_minimal and code != 'date_created' and code != 'time_created' and field_id != 1143 %} kp-offscreen{% endif %}"
)

# Replace all occurrences for minutes_ui_minimal
content = content.replace(
    "{% if minutes_ui_minimal and code != 'complainants' and code != 'respondents' and code != 'brgy_case_num' and code != 'purpose' and code != 'when' and code != 'what' and code != 'date_signed' and code != 'time_signed' %} kp-offscreen{% endif %}",
    "{% if minutes_ui_minimal and code != 'complainants' and code != 'respondents' and code != 'brgy_case_num' and code != 'purpose' and code != 'when' and code != 'what' and code != 'date_signed' and code != 'time_signed' and field_id != 1143 %} kp-offscreen{% endif %}"
)

# Write back
with open(r'c:\Users\panch\OneDrive\BaRUG v3 Jan 31\barug-for_lupon_updated\lupon_mem\templates\lupon_mem\form_builder.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed number field visibility for forms 9, 12, 33, 34, 42")
