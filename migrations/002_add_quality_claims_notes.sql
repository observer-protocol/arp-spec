-- Migration: Add quality_claims_notes table for VAC v0.3.2
-- Date: 2026-03-27
-- Description: Stores notes hashes for counterparty quality claims with retrieval tracking

-- Create the quality_claims_notes table
CREATE TABLE IF NOT EXISTS quality_claims_notes (
    notes_id SERIAL PRIMARY KEY,
    transaction_id VARCHAR(255) NOT NULL,
    notes_hash VARCHAR(64) NOT NULL,  -- SHA256 hash (64 hex characters)
    partner_id VARCHAR(255) NOT NULL,
    retrieval_url VARCHAR(512),
    retrieval_status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- 'pending', 'retrieved'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    retrieved_at TIMESTAMP WITH TIME ZONE,
    retrieved_by VARCHAR(255),
    
    -- Constraints
    CONSTRAINT valid_hash_length CHECK (LENGTH(notes_hash) = 64),
    CONSTRAINT valid_retrieval_status CHECK (retrieval_status IN ('pending', 'retrieved'))
);

-- Create indexes for efficient lookups
CREATE INDEX IF NOT EXISTS idx_quality_claims_notes_transaction 
    ON quality_claims_notes(transaction_id);

CREATE INDEX IF NOT EXISTS idx_quality_claims_notes_partner 
    ON quality_claims_notes(partner_id);

CREATE INDEX IF NOT EXISTS idx_quality_claims_notes_status 
    ON quality_claims_notes(retrieval_status);

-- Create unique constraint to prevent duplicate notes hashes per transaction/partner
CREATE UNIQUE INDEX IF NOT EXISTS idx_quality_claims_notes_unique 
    ON quality_claims_notes(transaction_id, partner_id);

-- Add comment describing table purpose
COMMENT ON TABLE quality_claims_notes IS 
    'Stores SHA256 hashes of counterparty notes for quality claims per VAC v0.3.2 spec §8.6';

-- Add comments on columns
COMMENT ON COLUMN quality_claims_notes.notes_hash IS 
    'SHA256 hash of freetext notes, verified when notes are submitted via POST /ars/notes/{transaction_id}';

COMMENT ON COLUMN quality_claims_notes.retrieval_status IS 
    'Status of notes retrieval: pending (hash stored, notes not yet submitted) or retrieved (notes verified and stored)';

COMMENT ON COLUMN quality_claims_notes.retrieval_url IS 
    'Optional AT ARS endpoint URL where notes can be retrieved';
