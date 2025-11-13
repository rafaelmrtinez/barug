-- Supabase SQL optimization for report_list performance
-- Run this in your Supabase SQL Editor

-- 1. Add indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_blotter_report_date_time 
ON blotter_report(date_time_reported DESC);

CREATE INDEX IF NOT EXISTS idx_blotter_report_subject_search 
ON blotter_report(incident_subject);

CREATE INDEX IF NOT EXISTS idx_payment_status_name 
ON payment_status(payment_status_name);

CREATE INDEX IF NOT EXISTS idx_blotter_report_payment_status 
ON blotter_report(payment_status_id);

-- 2. Composite indexes for common filter combinations
CREATE INDEX IF NOT EXISTS idx_blotter_report_date_payment 
ON blotter_report(date_time_reported DESC, payment_status_id);

-- 3. Analyze tables to update statistics (Supabase handles this automatically)
-- But you can manually trigger if needed:
-- ANALYZE blotter_report;
-- ANALYZE payment_status;

-- 4. Optional: Create a materialized view for faster reporting (if data doesn't change frequently)
-- CREATE MATERIALIZED VIEW report_list_view AS
-- SELECT 
--     br.blotter_report_id AS id,
--     COALESCE(br.incident_subject, '(no subject)') AS subject,
--     to_char(br.date_time_reported, 'YYYY-MM-DD HH24:MI') AS reported_at,
--     COALESCE(ps.payment_status_name, '') AS payment_status,
--     CASE 
--         WHEN ps.payment_status_name IS NULL OR ps.payment_status_name = '' THEN 'FOR LUPON REVIEW'
--         WHEN UPPER(ps.payment_status_name) IN ('PAID','UNPAID','DECLINED') THEN 'REVIEWED'
--         ELSE 'FOR LUPON REVIEW'
--     END AS blotter_status,
--     br.date_time_reported AS sort_date
-- FROM blotter_report br
-- LEFT JOIN payment_status ps ON ps.payment_status_id = br.payment_status_id
-- ORDER BY br.date_time_reported DESC;

-- 5. Create index on the materialized view if you use it
-- CREATE INDEX idx_report_list_view_date ON report_list_view(sort_date DESC);
-- CREATE INDEX idx_report_list_view_subject ON report_list_view(subject);
-- CREATE INDEX idx_report_list_view_payment ON report_list_view(payment_status);

COMMIT;