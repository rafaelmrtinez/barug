-- Updated confirm_report_and_open_case function
-- Add p_date_filed and p_time_filed parameters

CREATE OR REPLACE FUNCTION confirm_report_and_open_case(
  p_blotter_report_id INT,
  p_case_name TEXT,
  p_complaint_title_id INT,
  p_case_nature_id INT,
  p_settlement_status_id INT,
  p_added_by_staff_id INT,
  p_with_payment BOOLEAN DEFAULT FALSE,
  p_payment_receipt TEXT DEFAULT NULL,
  p_payment_amount NUMERIC DEFAULT 0,
  p_payment_status TEXT DEFAULT 'PAID',
  p_paid_by_person_id INT DEFAULT NULL,
  p_status_name_after TEXT DEFAULT 'ESCALATED TO CASE',
  p_status_remarks TEXT DEFAULT NULL,
  p_date_filed DATE DEFAULT NULL,  -- NEW PARAMETER
  p_time_filed TIME DEFAULT NULL   -- NEW PARAMETER
)
RETURNS INT
LANGUAGE plpgsql
AS $$
DECLARE
  v_case_id  INT;
  v_report   RECORD;
BEGIN
  -- 1) Load the report
  SELECT *
    INTO v_report
    FROM blotter_report
   WHERE blotter_report_id = p_blotter_report_id
   LIMIT 1;

  IF v_report IS NULL THEN
    RAISE EXCEPTION 'Report % not found', p_blotter_report_id;
  END IF;

  -- 2) Create case with user-provided date/time or defaults
  INSERT INTO blotter_case(
    blotter_case_name,
    date_filed, time_filed,
    incident_date, incident_time,
    incident_location, incident_desc,
    complaint_title_id, case_nature_id,
    blotter_report_id, settlement_status_id,
    added_by
  )
  VALUES (
    p_case_name,
    COALESCE(p_date_filed, CURRENT_DATE),      -- Use provided or default
    COALESCE(p_time_filed, CURRENT_TIME(0)),   -- Use provided or default
    v_report.incident_date, v_report.incident_time,
    NULL, v_report.incident_desc,
    p_complaint_title_id, p_case_nature_id,
    p_blotter_report_id, p_settlement_status_id,
    p_added_by_staff_id
  )
  RETURNING blotter_case_id INTO v_case_id;

  -- 3) Copy parties report -> case
  INSERT INTO complainant_case (blotter_case_id, person_id)
  SELECT v_case_id, cr.person_id
  FROM complainant_report cr
  WHERE cr.blotter_report_id = p_blotter_report_id
  ON CONFLICT DO NOTHING;

  INSERT INTO respondent_case (blotter_case_id, person_id)
  SELECT v_case_id, rr.person_id
  FROM respondent_report rr
  WHERE rr.blotter_report_id = p_blotter_report_id
  ON CONFLICT DO NOTHING;

  -- 4) Optional payment
  IF p_with_payment = TRUE AND p_payment_receipt IS NOT NULL THEN
    PERFORM record_case_payment(
      v_case_id, p_payment_receipt, p_payment_amount,
      COALESCE(p_payment_status, 'PAID'),
      p_paid_by_person_id, p_added_by_staff_id
    );
  END IF;

  -- 5) Append status trail ONLY (no cache column update)
  PERFORM set_report_status(
    p_blotter_report_id,
    p_status_name_after,
    p_status_remarks,
    p_added_by_staff_id
  );

  RETURN v_case_id;
END;
$$;
