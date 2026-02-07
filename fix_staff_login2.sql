-- Fix staff_login2 to fall back to staff.role_id if staff_role_assignment is empty
CREATE OR REPLACE FUNCTION staff_login2(
    p_username      TEXT,
    p_password      TEXT,
    p_ip_address    TEXT DEFAULT NULL,
    OUT user_id             INT,
    OUT person_id           INT,
    OUT user_type           TEXT,
    OUT role_name           TEXT,
    OUT first_name          TEXT,
    OUT middle_name         TEXT,
    OUT last_name           TEXT,
    OUT account_status_name TEXT,
    OUT login_log_id        INT
)
RETURNS SETOF RECORD
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_staff_id              INT;
    v_stored_password       TEXT;
    v_account_status_name   TEXT;
    v_user_type_id          INT;
    v_person_id             INT;
    v_first_name            TEXT;
    v_middle_name           TEXT;
    v_last_name             TEXT;
    v_role_names            TEXT;
    v_legacy_role_id        INT;
BEGIN
    IF p_username IS NULL OR length(btrim(p_username)) = 0 THEN
        RAISE EXCEPTION 'Username is required.' USING ERRCODE = 'P6001';
    END IF;

    IF p_password IS NULL OR length(p_password) = 0 THEN
        RAISE EXCEPTION 'Password is required.' USING ERRCODE = 'P6002';
    END IF;

    -- Locate staff credential + status + person info + legacy role_id
    SELECT s.staff_id,
           s.person_id,
           s.role_id,
           sc.passwordd,
           a.acc_status_name,
           p.first_name,
           p.middle_name,
           p.last_name
      INTO v_staff_id,
           v_person_id,
           v_legacy_role_id,
           v_stored_password,
           v_account_status_name,
           v_first_name,
           v_middle_name,
           v_last_name
      FROM staff_credential sc
      JOIN staff s          ON sc.staff_id = s.staff_id
      JOIN account_status a ON s.acc_status_id = a.acc_status_id
      JOIN person p         ON p.person_id   = s.person_id
     WHERE sc.username = lower(btrim(p_username))
     LIMIT 1;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Account does not exist.' USING ERRCODE = 'P6003';
    END IF;

    IF upper(coalesce(v_account_status_name, '')) NOT IN ('ACTIVE','PENDING') THEN
        RAISE EXCEPTION 'Account is not active. Please contact the administration.' USING ERRCODE = 'P6004';
    END IF;

    IF crypt(p_password, v_stored_password) <> v_stored_password THEN
        RAISE EXCEPTION 'Incorrect password.' USING ERRCODE = 'P6005';
    END IF;

    -- Try multi-role table first
    SELECT string_agg(DISTINCT r.role_name, ', ' ORDER BY r.role_name)
      INTO v_role_names
      FROM staff_role_assignment sra
      JOIN rolee r ON r.role_id = sra.role_id
     WHERE sra.staff_id  = v_staff_id
       AND sra.is_active = TRUE;

    -- Fall back to legacy staff.role_id if no multi-role assignments
    IF v_role_names IS NULL AND v_legacy_role_id IS NOT NULL THEN
        SELECT r.role_name
          INTO v_role_names
          FROM rolee r
         WHERE r.role_id = v_legacy_role_id;
    END IF;

    -- Final fallback
    IF v_role_names IS NULL THEN
        v_role_names := 'Unknown';
    END IF;

    SELECT ut.user_type_id
      INTO v_user_type_id
      FROM user_type ut
     WHERE upper(ut.user_type_name) = 'STAFF'
     LIMIT 1;

    IF v_user_type_id IS NULL THEN
        RAISE EXCEPTION 'User type STAFF is not configured.' USING ERRCODE = 'P6006';
    END IF;

    INSERT INTO public.login_log (login_time, user_id, user_type_id, ip_add)
    VALUES (CURRENT_TIMESTAMP, v_staff_id, v_user_type_id, p_ip_address::inet)
    RETURNING public.login_log.login_log_id INTO login_log_id;

    user_id             := v_staff_id;
    person_id           := v_person_id;
    user_type           := 'STAFF';
    role_name           := v_role_names;
    first_name          := v_first_name;
    middle_name         := v_middle_name;
    last_name           := v_last_name;
    account_status_name := v_account_status_name;

    RETURN NEXT;
END;
$$;
