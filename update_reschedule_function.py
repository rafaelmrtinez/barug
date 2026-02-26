import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'barug.settings')
django.setup()

from django.db import connection

sql = """
CREATE OR REPLACE FUNCTION public.fn_reschedule_hearing(
    p_notice_submission_id integer, 
    p_new_date date, 
    p_new_time time without time zone, 
    p_remarks text, 
    p_by_staff integer
)
RETURNS TABLE(success boolean, blotter_case_id integer, notice_sid integer, old_schedule text, new_schedule text, changed_at timestamp with time zone)
LANGUAGE plpgsql
AS $function$
DECLARE
  v_case_id          integer;
  v_form_id          integer;
  v_form_code        text;
  v_case_num         text;
  v_case_name        text;
  v_staff_name       text;
  v_old_date         text;
  v_old_time         text;
  v_new_date_text    text := to_char(p_new_date, 'YYYY-MM-DD');
  v_new_time_raw     text := to_char(p_new_time::time, 'HH24:MI');
  v_new_time_pretty  text := to_char(p_new_time::time, 'FMHH12:MI AM');
  v_month_txt        text := to_char(p_new_date, 'Month');
  v_day_txt          text := to_char(p_new_date, 'FMDD');
  v_year_txt         text := to_char(p_new_date, 'YYYY');
  v_now              timestamptz := now();
  v_cpt_resched_id   integer;
  v_message          text;
  v_old_sched        text;
  v_new_sched        text;
  v_sub_status       text;
  v_sub_submitted_at timestamptz;
  v_answers          jsonb;
  v_remarks_text     text;
BEGIN
  SELECT s.blotter_case_id, s.form_id, f.form_code, s.status, s.submitted_at
  INTO v_case_id, v_form_id, v_form_code, v_sub_status, v_sub_submitted_at
  FROM blotter_kp_submission s
  JOIN kp_form f ON f.form_id = s.form_id
  WHERE s.submission_id = p_notice_submission_id
  LIMIT 1;

  IF v_case_id IS NULL THEN
    RETURN QUERY SELECT FALSE, NULL::int, p_notice_submission_id, NULL::text, NULL::text, NULL::timestamptz;
    RETURN;
  END IF;

  IF UPPER(v_form_code) NOT IN ('KP-8','KP-12') THEN
    RAISE EXCEPTION 'fn_reschedule_hearing only supports KP-8 / KP-12 (got %)', v_form_code;
  END IF;

  SELECT m.hearing_date, m.hearing_time
  INTO v_old_date, v_old_time
  FROM fn_case_mediation_hearings(v_case_id) AS m
  WHERE m.notice_sid = p_notice_submission_id
  LIMIT 1;

  v_old_sched := COALESCE(NULLIF(trim(COALESCE(v_old_date,'') || ' ' || COALESCE(v_old_time,'')), ''), NULL);
  v_new_sched := trim(v_new_date_text || ' ' || v_new_time_pretty);

  UPDATE blotter_kp_answer a SET value_json = to_jsonb(v_new_date_text)
  FROM kp_field k
  WHERE a.submission_id = p_notice_submission_id AND a.field_id = k.field_id
    AND (LOWER(k.field_code) IN ('hearing_date','appearance_date','conciliation_date','date') OR a.field_id IN (42));

  UPDATE blotter_kp_answer a SET value_json = to_jsonb(v_month_txt)
  WHERE a.submission_id = p_notice_submission_id AND a.field_id IN (22,108);

  UPDATE blotter_kp_answer a SET value_json = to_jsonb(v_day_txt)
  WHERE a.submission_id = p_notice_submission_id AND a.field_id IN (176,166);

  UPDATE blotter_kp_answer a SET value_json = to_jsonb(v_year_txt)
  WHERE a.submission_id = p_notice_submission_id AND a.field_id IN (28,288);

  UPDATE blotter_kp_answer a SET value_json = to_jsonb(v_new_time_raw)
  FROM kp_field k
  WHERE a.submission_id = p_notice_submission_id AND a.field_id = k.field_id
    AND LOWER(k.field_code) IN ('hearing_time','appearance_time','time','session_time');

  IF UPPER(v_form_code) = 'KP-12' THEN
    UPDATE blotter_kp_answer a SET value_json = to_jsonb(v_new_time_raw)
    WHERE a.submission_id = p_notice_submission_id AND a.field_id IN (246,1122,188);
  END IF;

  SELECT case_progress_type_id INTO v_cpt_resched_id
  FROM case_progress_type WHERE UPPER(case_progress_type_name) = 'RESCHEDULED' LIMIT 1;

  -- Build standardized remarks: Hearing rescheduled from X to Y + newline + Reason: Z
  v_remarks_text := format('Hearing rescheduled from %s to %s', COALESCE(v_old_sched, '(none)'), v_new_sched);
  IF p_remarks IS NOT NULL AND btrim(p_remarks) != '' THEN
    v_remarks_text := v_remarks_text || chr(10) || 'Reason: ' || btrim(p_remarks);
  ELSE
    v_remarks_text := v_remarks_text || chr(10) || 'Reason: Rescheduled';
  END IF;

  IF v_cpt_resched_id IS NOT NULL THEN
    INSERT INTO case_progress_tracking(date_processed, remarks, case_progress_type_id, blotter_case_id, processed_by_id)
    VALUES (v_now, v_remarks_text, v_cpt_resched_id, v_case_id, p_by_staff);
  END IF;

  SELECT bc.blotter_case_num, bc.blotter_case_name INTO v_case_num, v_case_name
  FROM blotter_case bc WHERE bc.blotter_case_id = v_case_id LIMIT 1;

  IF p_by_staff IS NOT NULL THEN
    SELECT TRIM(CONCAT_WS(' ', p.first_name, NULLIF(SUBSTRING(COALESCE(p.middle_name, '') FROM 1 FOR 1) || '.',' .'), p.last_name, NULLIF(p.suffix, '')))
    INTO v_staff_name FROM staff s JOIN person p ON p.person_id = s.person_id WHERE s.staff_id = p_by_staff LIMIT 1;
  END IF;

  SELECT jsonb_agg(jsonb_build_object('label', COALESCE(kff.label_override, kf.base_label), 'value', a.value_json #>> '{}', 'field_code', kf.field_code) ORDER BY COALESCE(kff.sort_order,0), kf.field_code)
  INTO v_answers FROM blotter_kp_answer a JOIN kp_field kf ON kf.field_id = a.field_id
  LEFT JOIN kp_form_field kff ON kff.form_id = v_form_id AND kff.field_id = a.field_id
  WHERE a.submission_id = p_notice_submission_id;

  v_message := format('%s rescheduled %s hearing for Case %s  %s from %s to %s%s',
    COALESCE(v_staff_name, format('Staff ID %s', p_by_staff)), v_form_code,
    COALESCE(v_case_num, format('#%s', v_case_id)), COALESCE(v_case_name, 'Unnamed Case'),
    COALESCE(v_old_sched, '(none)'), v_new_sched,
    CASE WHEN p_remarks IS NULL OR btrim(p_remarks) = '' THEN '' ELSE format(' (remarks: %s)', p_remarks) END);

  PERFORM public.blotter_log_event('RESCHEDULE_HEARING'::text, 'blotter_case'::text, v_case_id,
    to_jsonb(v_message), p_by_staff, NULL::integer, 'hearing_schedule', v_old_sched, v_new_sched);

  RETURN QUERY SELECT TRUE, v_case_id, p_notice_submission_id, v_old_sched, v_new_sched, v_now;
END;
$function$;
"""

with connection.cursor() as cur:
    cur.execute(sql)
    print("Function fn_reschedule_hearing updated successfully!")
    print("Format: 'Hearing rescheduled from X to Y\\nReason: [reason or 'Rescheduled']'")
