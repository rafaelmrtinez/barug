-- Update KP8 form fields to show only required fields
-- Hide all fields first, then show only the 6 required ones

-- Hide all KP8 form fields by setting sort_order to 9999 (which effectively hides them)
UPDATE kp_form_field 
SET sort_order = 9999 
WHERE form_id = 8;

-- Show only the 6 required fields with proper sort order
UPDATE kp_form_field 
SET sort_order = 10 
WHERE form_id = 8 AND field_id = 1; -- Complainant(s)

UPDATE kp_form_field 
SET sort_order = 20 
WHERE form_id = 8 AND field_id = 2; -- Respondent(s)

UPDATE kp_form_field 
SET sort_order = 30 
WHERE form_id = 8 AND field_id = 12; -- Hearing Date

UPDATE kp_form_field 
SET sort_order = 40 
WHERE form_id = 8 AND field_id = 13; -- Hearing Time

UPDATE kp_form_field 
SET sort_order = 50 
WHERE form_id = 8 AND field_id = 42; -- Made this:

UPDATE kp_form_field 
SET sort_order = 60 
WHERE form_id = 8 AND field_id = 1121; -- Notified this:

-- Verify the changes
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
WHERE kff.form_id = 8
ORDER BY kff.sort_order, kff.kp_form_field_id;