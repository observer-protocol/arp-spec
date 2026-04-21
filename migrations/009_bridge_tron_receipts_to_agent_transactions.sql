-- Migration: Bridge tron_receipts → agent_transactions
-- Spec 2.5 Deliverable 2 & 4

-- ============================================================================
-- PART 1: Forward Bridge (tron_receipts → agent_transactions)
-- When a receipt is verified, insert into agent_transactions so dashboard picks it up
-- ============================================================================

CREATE OR REPLACE FUNCTION fn_tron_receipt_to_agent_transaction()
RETURNS TRIGGER AS $$
DECLARE
    v_agent_id VARCHAR;
    v_direction VARCHAR;
    v_counterparty VARCHAR;
BEGIN
    -- Only fire when the receipt transitions to verified = TRUE
    IF NEW.verified IS NOT DISTINCT FROM OLD.verified THEN
        RETURN NEW;
    END IF;

    IF NEW.verified IS NOT TRUE THEN
        RETURN NEW;
    END IF;

    -- Determine the agent_id and direction
    -- subject_did is the "about whom" — the agent whose reputation this counts for
    -- A receipt's subject received the payment; the issuer sent it
    v_agent_id := NEW.subject_agent_id;
    v_direction := 'receive';  -- subject is the receiver in the current receipt model
    v_counterparty := NEW.sender_address;

    -- If no agent_id, we cannot bridge — a receipt for an unknown agent
    IF v_agent_id IS NULL THEN
        RETURN NEW;
    END IF;

    -- Insert into agent_transactions if this tx_hash doesn't already exist
    INSERT INTO agent_transactions (
        agent_id, direction, counterparty_address,
        amount, asset, tx_hash, tron_status,
        network, rail, confirmations, block_number, timestamp,
        metadata, created_at
    )
    VALUES (
        v_agent_id, v_direction, v_counterparty,
        NEW.amount::numeric / 1000000.0,  -- TRC-20 6 decimals → human units
        NEW.asset, NEW.tron_tx_hash, 'confirmed',
        CASE WHEN NEW.network = 'mainnet' THEN 'tron:mainnet' ELSE 'tron:' || NEW.network END,
        NEW.rail, NEW.confirmations, NULL, NEW.tx_timestamp,
        jsonb_build_object(
            'source', 'tron_receipts_bridge',
            'receipt_id', NEW.receipt_id,
            'vc_id', NEW.vc_id,
            'issuer_did', NEW.issuer_did,
            'subject_did', NEW.subject_did,
            'has_vc', true
        ),
        NOW()
    )
    ON CONFLICT (tx_hash) DO UPDATE SET
        -- If a row already exists (chain listener got there first), enrich it with VC metadata
        metadata = agent_transactions.metadata ||
                   jsonb_build_object(
                       'receipt_id', NEW.receipt_id,
                       'vc_id', NEW.vc_id,
                       'issuer_did', NEW.issuer_did,
                       'subject_did', NEW.subject_did,
                       'has_vc', true
                   );

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION fn_tron_receipt_to_agent_transaction IS
    'Spec 2.5: Bridges verified tron_receipts into agent_transactions so dashboard picks them up';

-- Trigger: fire on INSERT or UPDATE of verified status
DROP TRIGGER IF EXISTS trg_tron_receipt_to_agent_transaction ON tron_receipts;
CREATE TRIGGER trg_tron_receipt_to_agent_transaction
    AFTER INSERT OR UPDATE ON tron_receipts
    FOR EACH ROW
    EXECUTE FUNCTION fn_tron_receipt_to_agent_transaction();

-- ============================================================================
-- PART 2: Reverse Bridge (agent_transactions enrichment)
-- When listener writes to agent_transactions, check if a receipt exists and enrich
-- ============================================================================

CREATE OR REPLACE FUNCTION fn_enrich_agent_transaction_with_vc()
RETURNS TRIGGER AS $$
DECLARE
    v_receipt RECORD;
BEGIN
    -- Only enrich if this row was inserted by the listener (no vc_id in metadata yet)
    IF NEW.metadata ? 'vc_id' THEN
        RETURN NEW;
    END IF;

    -- Look for a matching receipt
    SELECT receipt_id, vc_id, issuer_did, subject_did
    INTO v_receipt
    FROM tron_receipts
    WHERE tron_tx_hash = NEW.tx_hash AND verified = TRUE
    LIMIT 1;

    IF FOUND THEN
        NEW.metadata := NEW.metadata || jsonb_build_object(
            'receipt_id', v_receipt.receipt_id,
            'vc_id', v_receipt.vc_id,
            'issuer_did', v_receipt.issuer_did,
            'subject_did', v_receipt.subject_did,
            'has_vc', true
        );
    ELSE
        NEW.metadata := NEW.metadata || jsonb_build_object('has_vc', false);
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION fn_enrich_agent_transaction_with_vc IS
    'Spec 2.5: Enriches listener-detected agent_transactions with VC metadata when a matching receipt exists';

-- Trigger: fire BEFORE insert so metadata is set before the row is persisted
DROP TRIGGER IF EXISTS trg_enrich_agent_transaction_with_vc ON agent_transactions;
CREATE TRIGGER trg_enrich_agent_transaction_with_vc
    BEFORE INSERT ON agent_transactions
    FOR EACH ROW
    EXECUTE FUNCTION fn_enrich_agent_transaction_with_vc();
