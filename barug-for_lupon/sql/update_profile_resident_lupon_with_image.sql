-- Update profile_resident_lupon function to support person_img parameter
-- Run this in your Supabase SQL Editor

CREATE OR REPLACE FUNCTION profile_resident_lupon(
    p_performer_id integer,
    p_first_name text,
    p_middle_name text,
    p_last_name text,
    p_suffix text,
    p_birthdate date,
    p_sex_id integer,
    p_civil_status_id integer,
    p_nationality_id integer,
    p_religion_id integer,
    p_mobile_num text,
    p_email text,
    p_education_id integer,
    p_employment_status_id integer,
    p_residential_status_id integer,
    p_person_img text DEFAULT NULL
)
RETURNS void AS $$
BEGIN
    INSERT INTO person (
        first_name, 
        middle_name, 
        last_name, 
        suffix, 
        birthdate,
        sex_id, 
        civil_status_id, 
        nationality_id, 
        religion_id,
        mobile_num, 
        email, 
        education_id, 
        employment_status_id,
        residential_status_id, 
        added_by_id,
        person_img
    ) VALUES (
        p_first_name, 
        p_middle_name, 
        p_last_name, 
        p_suffix, 
        p_birthdate,
        p_sex_id, 
        p_civil_status_id, 
        p_nationality_id, 
        p_religion_id,
        p_mobile_num, 
        p_email, 
        p_education_id, 
        p_employment_status_id,
        p_residential_status_id, 
        p_performer_id,
        p_person_img
    );
END;
$$ LANGUAGE plpgsql;
