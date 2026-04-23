-- Create the missing fn_case_mediation_hearings function
-- This function returns hearing data for a specific case including schedule information

CREATE OR REPLACE FUNCTION fn_case_mediation_hearings(p_case_id INTEGER)
RETURNS TABLE (
    hearing_no INTEGER,
    source TEXT,
    notice_sid INTEGER,
    hearing_date DATE,
    hearing_time TIME,
    complainant_attended BOOLEAN,
    respondent_attended BOOLEAN,
    hearing_held BOOLEAN,
    held_at TIMESTAMP,
    remarks TEXT,
    settlement_outcome TEXT
) AS $$
BEGIN
    RETURN QUERY
    WITH forms AS (
        SELECT form_id, UPPER(form_code) AS code
        FROM kp_form
        WHERE UPPER(form_code) IN ('KP-8', 'KP-12')
    ),
    submissions AS (
        SELECT 
            s.submission_id,
            s.form_id,
            f.code AS source_code,
            s.blotter_case_id,
            s.submitted_at,
            ROW_NUMBER() OVER (
                PARTITION BY s.blotter_case_id 
                ORDER BY s.submitted_at ASC, s.submission_id ASC
            ) AS hearing_no
        FROM blotter_kp_submission s
        JOIN forms f ON f.form_id = s.form_id
        WHERE s.blotter_case_id = p_case_id
          AND UPPER(s.status) = 'SUBMITTED'
    ),
    answers AS (
        SELECT 
            s.submission_id,
            LOWER(kf.field_code) AS code,
            TRIM(BOTH '"' FROM a.value_json::text) AS v
        FROM submissions s
        JOIN blotter_kp_answer a ON a.submission_id = s.submission_id
        JOIN kp_field kf ON kf.field_id = a.field_id
        WHERE LOWER(kf.field_code) IN (
            'appearance_date', 'appearance_time',
            'hearing_date', 'hearing_time'
        )
    ),
    hearing_data AS (
        SELECT 
            s.hearing_no::INTEGER,
            s.source_code,
            s.submission_id,
            -- Extract hearing date
            COALESCE(
                (SELECT v FROM answers WHERE submission_id = s.submission_id AND code = 'hearing_date'),
                (SELECT v FROM answers WHERE submission_id = s.submission_id AND code = 'appearance_date')
            )::DATE AS hearing_date,
            -- Extract hearing time  
            COALESCE(
                (SELECT v FROM answers WHERE submission_id = s.submission_id AND code = 'hearing_time'),
                (SELECT v FROM answers WHERE submission_id = s.submission_id AND code = 'appearance_time')
            )::TIME AS hearing_time,
            s.submitted_at
        FROM submissions s
    ),
    attendance_data AS (
        SELECT 
            ha.notice_submission_id,
            ha.complainant_attended,
            ha.respondent_attended,
            ha.settlement_outcome,
            ha.remarks,
            ha.held_at
        FROM hearing_attendance ha
        WHERE ha.blotter_case_id = p_case_id
    ),
    progress_data AS (
        SELECT 
            cpt.blotter_case_id,
            cpt.date_processed,
            cpt.remarks
        FROM case_progress_tracking cpt
        JOIN case_progress_type t ON t.case_progress_type_id = cpt.case_progress_type_id
        WHERE cpt.blotter_case_id = p_case_id
          AND UPPER(t.case_progress_type_name) IN ('HEARING HELD', 'CONCILIATION HELD')
    )
    SELECT 
        hd.hearing_no,
        hd.source_code,
        hd.submission_id,
        hd.hearing_date,
        hd.hearing_time,
        COALESCE(ad.complainant_attended, FALSE),
        COALESCE(ad.respondent_attended, FALSE),
        CASE 
            WHEN ad.held_at IS NOT NULL THEN TRUE
            WHEN EXISTS (
                SELECT 1 FROM progress_data pd 
                WHERE pd.date_processed > hd.submitted_at
            ) THEN TRUE
            ELSE FALSE
        END,
        COALESCE(ad.held_at, (
            SELECT MAX(pd.date_processed) 
            FROM progress_data pd 
            WHERE pd.date_processed > hd.submitted_at
        )),
        COALESCE(ad.remarks, ''),
        COALESCE(ad.settlement_outcome, '')
    FROM hearing_data hd
    LEFT JOIN attendance_data ad ON ad.notice_submission_id = hd.submission_id
    ORDER BY hd.hearing_no;
END;
$$ LANGUAGE plpgsql;

-- Create the hearing_attendance table if it doesn't exist
CREATE TABLE IF NOT EXISTS hearing_attendance (
    blotter_case_id INTEGER NOT NULL,
    source_code TEXT NOT NULL,
    notice_submission_id INTEGER NOT NULL,
    held_at TIMESTAMPTZ DEFAULT NOW(),
    complainant_attended BOOLEAN DEFAULT FALSE,
    respondent_attended BOOLEAN DEFAULT FALSE,
    settlement_outcome TEXT,
    remarks TEXT
);

-- Create index for better performance
CREATE INDEX IF NOT EXISTS idx_hearing_attendance_case_notice 
ON hearing_attendance(blotter_case_id, notice_submission_id);