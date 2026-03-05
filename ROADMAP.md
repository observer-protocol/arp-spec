# Observer Protocol Roadmap — Addressing Technical Review

**Date:** March 4, 2026  
**Based on:** Feedback from arc0btc technical review  
**Current Status:** MVP/alpha (launched Feb 22, 2026)

---

## Phase 1: Immediate Fixes (Weeks 1-2)

### 1.1 Fix "Stub Verification" UI/UX
**Problem:** "Verified" badge implies cryptographic proof that doesn't exist yet  
**Solution:** Update badge system to show stages:
- **"Registered"** — Agent has registered, basic identity established
- **"Verification Pending"** — Registered, awaiting cryptographic proof  
- **"Verified"** — Full challenge-response verification complete

**Files to update:**
- Badge generation endpoint
- API response for agent status
- Web UI if applicable

**Effort:** 1-2 days

### 1.2 Documentation Transparency
**Problem:** Whitepaper exists but may not be discoverable  
**Solution:** 
- Prominently link whitepaper in README
- Add "Current Limitations" section to docs
- Document MVP status clearly: "Registration working, cryptographic verification coming"

**Effort:** 1 day

---

## Phase 2: Core Cryptographic Implementation (Weeks 3-6)

### 2.1 Real Challenge-Response Verification
**Problem:** Currently accepts "any non-empty signature"  
**Solution:** Implement proper challenge-response:

```
1. Server generates challenge: random nonce + timestamp
2. Agent signs challenge with private key
3. Server verifies signature against registered public key
4. Challenge marked as used (prevent replay)
5. Agent status upgraded to "Verified"
```

**Technical requirements:**
- Ed25519 or secp256k1 key pairs
- Challenge storage (Redis/DB) with TTL
- Signature verification library
- Nonce uniqueness enforcement

**Effort:** 1-2 weeks

### 2.2 Replay Protection
**Problem:** Captured challenges could be replayed  
**Solution (arc0btc's recommendation):**
- **Time-bounded:** 5-minute expiry on challenges
- **Single-use nonce:** Each challenge can only be used once
- **Storage:** Used challenges stored with cleanup job

**Implementation:**
```python
challenge = {
    "nonce": generate_secure_random(32),
    "created_at": timestamp(),
    "expires_at": timestamp() + 300,  # 5 min
    "used": False
}
```

**Effort:** 2-3 days

### 2.3 Key Rotation Support
**Problem:** No way to rotate keys if compromised  
**Solution:** 
- Allow agents to submit new public keys
- Old attestations remain valid (linked to old key)
- New attestations use new key
- Historical verification trail maintained

**Effort:** 3-5 days

---

## Phase 3: Team & Transparency (Weeks 4-8)

### 3.1 Team GitHub Profiles
**Problem:** No verifiable contributor history  
**Solution:**
- Boyd: Use existing GitHub profile (public ArcadiaB activity)
- Maxi: Create dedicated bot/agent profile that documents:
  - Purpose
  - Human operator (Boyd)
  - Autonomous capabilities
  - Contact method

**Effort:** 1 day setup

### 3.2 Open Source Governance
**Problem:** Single-contributor project perception  
**Solution:**
- CONTRIBUTING.md with clear guidelines
- Issue templates for bug reports/feature requests
- Public roadmap (this document)
- Regular dev updates (weekly/bi-weekly)

**Effort:** 2-3 days

---

## Phase 4: Security Hardening (Weeks 6-10)

### 4.1 Security Audit
**Problem:** No third-party security review  
**Solution:**
- Engage security researcher for code review
- Focus areas: signature verification, replay protection, API auth
- Budget: $2,000-5,000 for initial audit
- Target: Before "v1.0" release

**Effort:** 1-2 weeks (external dependency)

### 4.2 Rate Limiting & Abuse Prevention
**Problem:** Open API could be spammed  
**Solution:**
- IP-based rate limiting
- Registration throttling
- Challenge generation limits
- Cost to register (small Lightning payment?)

**Effort:** 3-5 days

### 4.3 Database Security
**Problem:** Agent data protection  
**Solution:**
- Encrypt sensitive fields at rest
- Secure API key storage (hash, not plaintext)
- Access logging
- Backup encryption

**Effort:** 2-3 days

---

## Phase 5: Production Readiness (Weeks 8-12)

### 5.1 Re-invite Technical Reviewers
**Goal:** Get arc0btc and others to re-audit  
**Trigger:** When challenge-response is live  
**Approach:**
- Comment on original review threads
- Post update on Nostr/X
- Request specific feedback on cryptographic implementation

**Effort:** 1 day outreach

### 5.2 Integration Examples
**Goal:** Show real usage, not just API docs  
**Deliverables:**
- Working example: Agent A pays Agent B with verification
- Video walkthrough
- Simple web UI for viewing reputation graphs
- MCP server integration example

**Effort:** 1-2 weeks

### 5.3 Performance & Scaling
**Problem:** Current setup is single-server  
**Solution:**
- Load testing
- Database optimization
- CDN for static assets
- Monitoring/alerting

**Effort:** 1-2 weeks

---

## Milestones & Timeline

| Phase | Target Date | Key Deliverable |
|-------|-------------|-----------------|
| Phase 1 | March 18 | UI shows "Registered" vs "Verified" |
| Phase 2 | April 1 | Working challenge-response verification |
| Phase 3 | April 15 | Team profiles, open governance |
| Phase 4 | May 1 | Security audit complete |
| Phase 5 | May 15 | Production v1.0, re-invite reviewers |

---

## Resource Requirements

### Development Time
- **Phase 1-2:** 3-4 weeks of focused dev work
- **Phase 3:** 1 week (mostly documentation)
- **Phase 4:** 2 weeks (1 week dev, 1 week audit)
- **Phase 5:** 2-3 weeks

**Total:** ~8-10 weeks to production-ready

### Budget
- Security audit: $2,000-5,000
- Infrastructure (if scaling): $100-300/month
- Developer time: Boyd's time + possibly contract help for cryptography

### Dependencies
- arc0btc or similar for re-review
- Security auditor availability
- Lightning Wallet MCP stability (we depend on it)

---

## Success Metrics

- [ ] Challenge-response verification working end-to-end
- [ ] arc0btc satisfied with implementation
- [ ] 10+ agents successfully verified
- [ ] 100+ attestations recorded
- [ ] Security audit passed
- [ ] No critical vulnerabilities reported
- [ ] Community contributors beyond core team

---

## Immediate Next Steps (This Week)

1. **Update API/UI** — Change "verified" to "registered" until crypto proof implemented
2. **Document current state** — Add "MVP Limitations" section to README
3. **Design challenge-response protocol** — Spec out the cryptographic flow
4. **Create GitHub issue** — Public roadmap tracking
5. **Update arc0btc** — Share this roadmap, invite feedback

---

## Long-Term Vision (Beyond v1.0)

- **Multi-signature verification** — Require multiple attesters for high-value agents
- **ZK proofs** — Privacy-preserving verification (agent proves reputation without revealing all transactions)
- **Cross-chain attestations** — Bridge to other L1s/L2s
- **Decentralized registry** — Move from single-server to distributed consensus

But first: Nail the basics. Get challenge-response right. Earn trust through shipping, not promises.
