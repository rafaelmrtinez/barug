-- Drop existing function if it exists
DROP FUNCTION IF EXISTS set_blotter_case_num() CASCADE;

-- Create new function with YY-MM-### format
CREATE OR REPLACE FUNCTION set_blotter_case_num()
RETURNS TRIGGER AS $$
DECLARE
    year_prefix TEXT;
    month_prefix TEXT;
    next_num INTEGER;
    new_case_num TEXT;
BEGIN
    -- Only generate if blotter_case_num is NULL
    IF NEW.blotter_case_num IS NULL THEN
        -- Get current year (last 2 digits) and month
        year_prefix := TO_CHAR(CURRENT_DATE, 'YY');
        month_prefix := TO_CHAR(CURRENT_DATE, 'MM');
        
        -- Get the next case number for this year-month
        SELECT COALESCE(MAX(
            CAST(
                SUBSTRING(blotter_case_num FROM '\d+$') AS INTEGER
            )
        ), 0) + 1
        INTO next_num
        FROM blotter_case
        WHERE blotter_case_num LIKE year_prefix || '-' || month_prefix || '-%';
        
        -- Format: YY-MM-NNN (e.g., 26-01-001)
        new_case_num := year_prefix || '-' || month_prefix || '-' || LPAD(next_num::TEXT, 3, '0');
        
        NEW.blotter_case_num := new_case_num;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Recreate the trigger
DROP TRIGGER IF EXISTS trg_set_case_num ON blotter_case;
CREATE TRIGGER trg_set_case_num 
    BEFORE INSERT ON blotter_case 
    FOR EACH ROW 
    EXECUTE FUNCTION set_blotter_case_num();
