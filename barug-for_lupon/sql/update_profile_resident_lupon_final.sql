-- Add person_img parameter to profile_resident_lupon function
-- Run this in Supabase SQL Editor

CREATE OR REPLACE FUNCTION profile_resident_lupon(
  p_performer_id INT,
  p_first_name TEXT,
  p_middle_name TEXT,
  p_last_name TEXT,
  p_suffix TEXT,
  p_birthdate DATE,
  p_sex_id INT,
  p_civil_status_id INT,
  p_nationality_id INT,
  p_religion_id INT,
  p_mobile_num TEXT,
  p_email TEXT,
  p_education_id INT,
  p_employment_status_id INT,
  p_residential_status_id INT,
  p_person_img TEXT DEFAULT NULL  -- ADD THIS LINE
)
RETURNS INT AS $$
DECLARE
  v_person_id               INT;
  v_now                     TIMESTAMPTZ := now();
  v_user_type_id_staff      INT;
  v_subsystem_resprof_id    INT;
  v_person_status_active_id INT;
  v_fullname                TEXT;
BEGIN
  SELECT user_type_id INTO v_user_type_id_staff FROM user_type WHERE user_type_name = 'STAFF' LIMIT 1;
  SELECT log_subsystem_id INTO v_subsystem_resprof_id FROM log_subsystem WHERE log_subsystem_name = 'RESIDENT PROFILING' LIMIT 1;
  v_person_status_active_id := 1;

  p_last_name  := upper(p_last_name);
  p_first_name := upper(p_first_name);
  IF p_middle_name IS NOT NULL THEN p_middle_name := upper(p_middle_name); END IF;
  IF p_suffix IS NOT NULL THEN p_suffix := upper(p_suffix); END IF;

  INSERT INTO person (
    last_name, first_name, middle_name, suffix, birthdate, email, mobile_num,
    sex_id, person_status_id, residential_status_id, civil_status_id,
    nationality_id, religion_id, education_id, employment_status_id,
    added_by_id, official_reg_date, person_img  -- ADD person_img HERE
  ) VALUES (
    p_last_name, p_first_name, p_middle_name, p_suffix, p_birthdate, p_email, p_mobile_num,
    p_sex_id, v_person_status_active_id, p_residential_status_id, p_civil_status_id,
    p_nationality_id, p_religion_id, p_education_id, p_employment_status_id,
    p_performer_id, v_now::date, p_person_img  -- ADD p_person_img HERE
  )
  RETURNING person_id INTO v_person_id;

  SELECT first_name || ' ' || COALESCE(SUBSTRING(middle_name FROM 1 FOR 1) || '. ', '') || last_name || COALESCE(', ' || NULLIF(suffix, ''), '')
  INTO v_fullname FROM person WHERE person_id = v_person_id;

  INSERT INTO common_log (record_affected_id, details, table_affected, action, performer_id, user_type_id, subsystem, date_time, new_value)
  VALUES (v_person_id, 'Lupon profile added for ' || v_fullname, 'PERSON', 'INSERT', p_performer_id, v_user_type_id_staff, v_subsystem_resprof_id, v_now, json_build_object('residential_status_id', p_residential_status_id)::text);

  RETURN v_person_id;
END;
$$ LANGUAGE plpgsql;
