from django.db import migrations

class Migration(migrations.Migration):
    dependencies = []

    operations = [
        migrations.RunSQL(
            sql="""
            DROP FUNCTION IF EXISTS get_Schedule_timeline(INT);
            
            CREATE FUNCTION get_Schedule_timeline(p_case_id INT)
            RETURNS TABLE(
                event_seq INT,
                event_kind TEXT,
                source TEXT,
                notice_sid INT,
                old_schedule TEXT,
                new_schedule TEXT,
                event_at TIMESTAMPTZ,
                staff_name TEXT,
                log_message TEXT
            ) AS $$
            BEGIN
                RETURN QUERY
                WITH schedule_events AS (
                    -- KP-8 forms (mediation hearing notices)
                    SELECT
                        s.submission_id,
                        'KP-8' AS source,
                        s.submitted_at AS event_time,
                        s.submitted_by_id,
                        (SELECT value_json::text FROM blotter_kp_answer a 
                         JOIN kp_field f ON f.field_id = a.field_id 
                         WHERE a.submission_id = s.submission_id 
                         AND LOWER(f.field_code) IN ('hearing_date', 'appearance_date') 
                         LIMIT 1) AS sched_date,
                        (SELECT value_json::text FROM blotter_kp_answer a 
                         JOIN kp_field f ON f.field_id = a.field_id 
                         WHERE a.submission_id = s.submission_id 
                         AND LOWER(f.field_code) IN ('hearing_time', 'appearance_time') 
                         LIMIT 1) AS sched_time
                    FROM blotter_kp_submission s
                    JOIN kp_form kf ON kf.form_id = s.form_id
                    WHERE s.blotter_case_id = p_case_id
                    AND UPPER(kf.form_code) = 'KP-8'
                    AND s.status = 'SUBMITTED'
                    
                    UNION ALL
                    
                    -- KP-12 forms (conciliation hearing notices)
                    SELECT
                        s.submission_id,
                        'KP-12' AS source,
                        s.submitted_at AS event_time,
                        s.submitted_by_id,
                        (SELECT value_json::text FROM blotter_kp_answer a 
                         JOIN kp_field f ON f.field_id = a.field_id 
                         WHERE a.submission_id = s.submission_id 
                         AND LOWER(f.field_code) IN ('hearing_date', 'appearance_date') 
                         LIMIT 1) AS sched_date,
                        (SELECT value_json::text FROM blotter_kp_answer a 
                         JOIN kp_field f ON f.field_id = a.field_id 
                         WHERE a.submission_id = s.submission_id 
                         AND LOWER(f.field_code) IN ('hearing_time', 'appearance_time') 
                         LIMIT 1) AS sched_time
                    FROM blotter_kp_submission s
                    JOIN kp_form kf ON kf.form_id = s.form_id
                    WHERE s.blotter_case_id = p_case_id
                    AND UPPER(kf.form_code) = 'KP-12'
                    AND s.status = 'SUBMITTED'
                )
                SELECT
                    ROW_NUMBER() OVER (ORDER BY se.event_time)::INT AS event_seq,
                    'SET'::TEXT AS event_kind,
                    se.source,
                    se.submission_id AS notice_sid,
                    NULL::TEXT AS old_schedule,
                    TRIM(BOTH '"' FROM COALESCE(se.sched_date, '')) || ' ' || 
                    TRIM(BOTH '"' FROM COALESCE(se.sched_time, '')) AS new_schedule,
                    se.event_time,
                    CASE 
                        WHEN se.submitted_by_id IS NOT NULL THEN
                            (SELECT p.last_name || ', ' || p.first_name 
                             FROM staff st 
                             JOIN person p ON p.person_id = st.person_id 
                             WHERE st.staff_id = se.submitted_by_id)
                        ELSE NULL
                    END AS staff_name,
                    'Hearing scheduled via ' || se.source AS log_message
                FROM schedule_events se
                WHERE se.sched_date IS NOT NULL
                ORDER BY se.event_time;
            END;
            $$ LANGUAGE plpgsql;
            """,
            reverse_sql="DROP FUNCTION IF EXISTS get_Schedule_timeline(INT);"
        ),
    ]
