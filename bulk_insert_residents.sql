-- Bulk insert residents for profiling
-- Based on the profile_resident_lupon function used in http://192.168.8.105:8005/lupon_mem/profiling/personal-info/

DO $$
DECLARE
    v_performer_id INT := 13; -- STAFF_SYSTEM_ID from settings
    resident_names TEXT[][] := ARRAY[
        ['RHEA', NULL, 'DECIERDO'],
        ['HENDRICK', NULL, 'ARCILLA'],
        ['KURT JOHN', 'L.', 'LUZADA'],
        ['FILICITY', NULL, 'NABUA'],
        ['JEROME', NULL, 'BRIONES'],
        ['PERCITO', NULL, 'MERCADER'],
        ['JASMINE', NULL, 'MAMAC'],
        ['HENCEL', NULL, 'ORTEGA'],
        ['CHIERYL', NULL, 'QUIRANTE'],
        ['JUDY', NULL, 'ALISON'],
        ['MARJORIE', NULL, 'ALISON'],
        ['AIZA', NULL, 'LAROBIS'],
        ['MARYJOY', NULL, 'MANGUBAT'],
        ['MADALYN SEJANE', NULL, 'VENDER'],
        ['MERLISA', NULL, 'TOBIANO'],
        ['JONIE', NULL, 'CABATAÑA'],
        ['PRINCESS MAE', NULL, 'LOBITAÑA'],
        ['RODOLFO', 'S.', 'FRANCO'],
        ['BILL', NULL, 'DOUGLASGO'],
        ['ANGELO', NULL, 'IGOT'],
        ['ERWIN', NULL, 'MANGUILIMOTAN'],
        ['JOHN PAUL ENTRINA', NULL, 'SIBLANG'],
        ['SWETY', NULL, 'BARRIENTOS'],
        ['JOHN MARK', NULL, 'BARRIENTOS'],
        ['GENEVIB', NULL, 'BAGUIO'],
        ['JASON', NULL, 'LASMARIAS'],
        ['MARIA TERESA', 'S.', 'BAUTISTA'],
        ['MARY GRACE', NULL, 'BARRIENTOS'],
        ['JOAN', NULL, 'LASMARIAS']
    ];
    i INT;
    v_first_name TEXT;
    v_middle_name TEXT;
    v_last_name TEXT;
    v_person_id INT;
BEGIN
    FOR i IN 1..array_length(resident_names, 1) LOOP
        -- Parse names (all arrays now have 3 elements)
        v_first_name := resident_names[i][1];
        v_middle_name := resident_names[i][2];
        v_last_name := resident_names[i][3];

        -- Check if resident already exists to avoid duplicates
        SELECT person_id INTO v_person_id 
        FROM person 
        WHERE UPPER(first_name) = UPPER(v_first_name) 
          AND UPPER(last_name) = UPPER(v_last_name)
          AND (v_middle_name IS NULL OR UPPER(COALESCE(middle_name, '')) = UPPER(v_middle_name))
        LIMIT 1;

        -- Only insert if not exists
        IF v_person_id IS NULL THEN
            SELECT profile_resident_lupon(
                p_performer_id := v_performer_id,
                p_first_name := v_first_name,
                p_middle_name := v_middle_name,
                p_last_name := v_last_name,
                p_suffix := NULL,
                p_birthdate := '2000-01-01'::DATE,
                p_sex_id := 1, -- Default to Male, can be updated later
                p_civil_status_id := 1, -- Single
                p_nationality_id := 7, -- Filipino
                p_religion_id := 12, -- Roman Catholic
                p_mobile_num := NULL,
                p_email := NULL,
                p_education_id := NULL,
                p_employment_status_id := NULL,
                p_residential_status_id := 2, -- Resident
                p_person_img := NULL
            ) INTO v_person_id;
            
            RAISE NOTICE 'Added resident: % % (ID: %)', v_first_name, v_last_name, v_person_id;
        ELSE
            RAISE NOTICE 'Skipped duplicate: % %', v_first_name, v_last_name;
        END IF;
    END LOOP;
    
    RAISE NOTICE 'Bulk insert completed!';
END $$;