-- SQL script to optimize report_list performance
-- Run this in your PostgreSQL database

-- Add indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_blotter_report_date_time ON blotter_report(date_time_reported DESC);
CREATE INDEX IF NOT EXISTS idx_blotter_report_subject ON blotter_report USING gin(to_tsvector('english', incident_subject));
CREATE INDEX IF NOT EXISTS idx_payment_status_name ON payment_status(payment_status_name);
CREATE INDEX IF NOT EXISTS idx_blotter_report_payment_status ON blotter_report(payment_status_id);

-- Additional composite indexes for common filter combinations
CREATE INDEX IF NOT EXISTS idx_blotter_report_date_payment ON blotter_report(date_time_reported DESC, payment_status_id);
CREATE INDEX IF NOT EXISTS idx_blotter_report_subject_date ON blotter_report(incident_subject, date_time_reported DESC);

-- Analyze tables to update statistics
ANALYZE blotter_report;
ANALYZE payment_status;