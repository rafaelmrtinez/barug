-- Create table for case documents (final copies, etc.)
CREATE TABLE IF NOT EXISTS case_document (
    case_document_id SERIAL PRIMARY KEY,
    blotter_case_id INT NOT NULL REFERENCES blotter_case(blotter_case_id) ON DELETE CASCADE,
    document_type VARCHAR(50) NOT NULL DEFAULT 'FINAL_COPY', -- FINAL_COPY, SETTLEMENT_COPY, etc.
    file_name VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL, -- Supabase public URL or local path
    mime_type VARCHAR(100),
    file_size_bytes BIGINT,
    uploaded_by_id INT REFERENCES staff(staff_id),
    uploaded_at TIMESTAMPTZ DEFAULT NOW(),
    description TEXT,
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMPTZ,
    deleted_by_id INT REFERENCES staff(staff_id)
);

-- Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_case_document_case_id ON case_document(blotter_case_id);
CREATE INDEX IF NOT EXISTS idx_case_document_type ON case_document(document_type);
CREATE INDEX IF NOT EXISTS idx_case_document_uploaded_at ON case_document(uploaded_at DESC);

-- Add comment
COMMENT ON TABLE case_document IS 'Stores uploaded documents for cases (final copies, settlement documents, etc.)';
