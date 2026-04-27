/**
 * Outbound Payment Tracking Patch for LND Observer Listener
 *
 * Add this code to lnd-observer-listener.mjs to track outbound payments
 * (Maxi sending sats to others).
 *
 * INSTRUCTIONS:
 * 1. Add getNewOutboundPayments() function after getNewSettledInvoices()
 * 2. Add processOutboundPayment() function after processInvoice()
 * 3. Add outbound poll to pollCycle() after the inbound invoice processing
 * 4. Add lastPaymentIndex to the state object in loadState()
 *
 * Or: replace the entire listener with lnd-observer-listener-v2.mjs
 */

// ── Add to loadState() default state: ────────────────────────
// lastPaymentIndex: 0,
// processedOutboundHashes: [],

// ── New function: Get outbound payments ──────────────────────

async function getNewOutboundPayments(lastIndex) {
  try {
    const data = await lndRequest('GET', `/v1/payments?include_incomplete=false&max_payments=50&reversed=true`);
    const payments = data.payments || [];

    // Filter for successful payments after lastIndex
    const newPayments = payments.filter(p =>
      p.status === 'SUCCEEDED' &&
      parseInt(p.payment_index || '0') > lastIndex
    );

    return newPayments.sort((a, b) =>
      parseInt(a.payment_index || '0') - parseInt(b.payment_index || '0')
    );
  } catch (e) {
    log('error', `Failed to fetch outbound payments: ${e.message}`);
    return [];
  }
}

// ── New function: Process outbound payment ───────────────────

async function processOutboundPayment(payment, state) {
  const paymentHash = payment.payment_hash;

  // Check if already processed
  if (state.processedOutboundHashes && state.processedOutboundHashes.includes(paymentHash)) {
    return false;
  }

  const amountSats = parseInt(payment.value_sat || payment.value || '0');
  const timestamp = new Date(parseInt(payment.creation_date) * 1000).toISOString();
  const preimage = payment.payment_preimage || null;

  log('info', `Processing outbound payment: ${paymentHash.substring(0, 16)}...`);
  log('info', `  Amount: ${amountSats} sats (outbound)`);

  // Build attestation for outbound payment
  const attestation = {
    agent_id: CONFIG.agentId,
    protocol: 'lightning',
    transaction_reference: paymentHash,
    timestamp: timestamp,
    preimage: preimage,
    direction: 'outbound',
    amount_sats: amountSats,
    counterparty: null,
    memo: payment.memo || null,
    public_key: PUBLIC_KEY_HEX,
  };

  const message = JSON.stringify(attestation);
  const signature = await createRealSignature(message);

  const params = new URLSearchParams({
    agent_id: attestation.agent_id,
    protocol: attestation.protocol,
    transaction_reference: attestation.transaction_reference,
    timestamp: attestation.timestamp,
    signature: signature,
    optional_metadata: JSON.stringify({
      preimage: attestation.preimage,
      direction: 'outbound',
      amount_sats: attestation.amount_sats,
      counterparty: attestation.counterparty,
      memo: attestation.memo,
      service_description: null,
    }),
  });

  const url = `${CONFIG.observerProtocolUrl}/observer/submit-transaction?${params.toString()}`;

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Accept': 'application/json' },
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`HTTP ${response.status}: ${errorText}`);
    }

    const result = await response.json();
    log('info', `  ✓ Outbound payment submitted`, { event_id: result.event_id });

    // Update state
    if (!state.processedOutboundHashes) state.processedOutboundHashes = [];
    state.processedOutboundHashes.push(paymentHash);
    state.lastPaymentIndex = Math.max(
      state.lastPaymentIndex || 0,
      parseInt(payment.payment_index || '0')
    );
    state.totalSubmitted++;
    saveState(state);

    return true;
  } catch (e) {
    log('error', `  ✗ Failed to submit outbound payment: ${e.message}`);
    return false;
  }
}

// ── Add to pollCycle() after inbound invoice processing: ─────

async function pollOutbound(state) {
  const lastIdx = state.lastPaymentIndex || 0;
  log('info', `Polling for outbound payments (last index: ${lastIdx})...`);

  const payments = await getNewOutboundPayments(lastIdx);

  if (payments.length === 0) {
    log('info', 'No new outbound payments found');
    return;
  }

  log('info', `Found ${payments.length} new outbound payment(s)`);

  for (const payment of payments) {
    await processOutboundPayment(payment, state);
  }
}

// Then in pollCycle(), add after the inbound processing:
// await pollOutbound(state);

export { getNewOutboundPayments, processOutboundPayment, pollOutbound };
