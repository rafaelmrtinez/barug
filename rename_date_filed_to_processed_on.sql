-- Migration: Rename date_filed display to processed_on
-- The actual date_filed and time_filed columns already exist and contain the correct data
-- This migration updates queries to use date_time_added for "processed on" display

-- Note: No schema changes needed - just query updates in application code
-- The blotter_case table already has:
--   - date_filed (DATE) - actual filing date
--   - time_filed (TIME) - actual filing time  
--   - date_time_added (TIMESTAMP) - when record was processed/added to system

-- Application code should use:
--   - date_time_added for "Processed On" display (when case was added to system)
--   - date_filed + time_filed for actual filing date/time
