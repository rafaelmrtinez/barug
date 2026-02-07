-- Performance Indexes for Case Detail Page
-- Run this SQL to add indexes that will dramatically speed up case detail queries

-- Index for case submissions lookup
CREATE INDEX IF NOT EXISTS idx_submission_case_id 
ON blotter_kp_submission(blotter_case_id);

-- Index for submission status filtering
CREATE INDEX IF NOT EXISTS idx_submission_status 
ON blotter_kp_submission(status);

-- Index for form ID lookups
CREATE INDEX IF NOT EXISTS idx_submission_form_id 
ON blotter_kp_submission(form_id);

-- Index for answer lookups by submission
CREATE INDEX IF NOT EXISTS idx_answer_submission_id 
ON blotter_kp_answer(submission_id);

-- Index for answer lookups by field
CREATE INDEX IF NOT EXISTS idx_answer_field_id 
ON blotter_kp_answer(field_id);

-- Composite index for audit field lookups (fields 1120, 1121, 1122)
CREATE INDEX IF NOT EXISTS idx_answer_audit_fields 
ON blotter_kp_answer(submission_id, field_id) 
WHERE field_id IN (1120, 1121, 1122);

-- Index for form code lookups
CREATE INDEX IF NOT EXISTS idx_form_code 
ON kp_form(form_code);

-- Index for submitted_at timestamp
CREATE INDEX IF NOT EXISTS idx_submission_submitted_at 
ON blotter_kp_submission(submitted_at);

-- Composite index for case + form code queries
CREATE INDEX IF NOT EXISTS idx_submission_case_form 
ON blotter_kp_submission(blotter_case_id, form_id);

-- Analyze tables to update statistics
ANALYZE blotter_kp_submission;
ANALYZE blotter_kp_answer;
ANALYZE kp_form;
ANALYZE blotter_case;
