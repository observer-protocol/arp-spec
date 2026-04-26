/**
 * Observer Protocol JavaScript SDK — TypeScript definitions
 */

export class ObserverError extends Error {
  statusCode: number;
  detail: string;
  constructor(statusCode: number, detail: string);
}

export interface RegisterAgentParams {
  publicKey: string;
  agentName?: string;
  alias?: string;
  framework?: string;
}

export interface Agent {
  agentId: string;
  agentDid: string;
  agentName?: string;
  didDocument?: Record<string, any>;
  verificationStatus?: string;
}

export interface AgentProfile {
  agentId: string;
  agentName: string | null;
  did: string;
  verified: boolean;
  trustScore: number | null;
  rails: string[] | null;
  transactionCount: number;
  attestationCount: number;
}

export interface Challenge {
  challengeId: string;
  nonce: string;
  expiresAt: string;
}

export interface TrustScoreComponents {
  receipt_score: number;
  counterparty_score: number;
  org_score: number;
  recency_score: number;
  volume_score: number;
}

export interface TrustScore {
  agentId: string;
  trustScore: number;
  receiptCount: number;
  uniqueCounterparties: number;
  totalStablecoinVolume: string;
  lastActivity: string | null;
  components: TrustScoreComponents | null;
}

export interface ChainVerification {
  verified: boolean;
  chain: string;
  receiptReference: string;
  transactionReference: string | null;
  explorerUrl: string | null;
  confirmedAt: string | null;
  chainSpecific: Record<string, any>;
  idempotentReplay: boolean;
}

export interface AuditEvent {
  eventId: string;
  receiptReference: string;
  dashboardUrl: string;
  idempotentReplay: boolean;
}

export interface ClientOptions {
  baseUrl?: string;
  apiKey?: string;
  timeout?: number;
}

export class ObserverClient {
  constructor(options?: ClientOptions);

  // Registration
  registerAgent(params: RegisterAgentParams): Promise<Agent>;
  requestChallenge(agentId: string): Promise<Challenge>;
  verifyAgent(agentId: string, signedChallenge: string): Promise<Record<string, any>>;

  // Profile
  getAgent(agentId: string): Promise<AgentProfile>;
  getDIDDocument(agentId: string): Promise<Record<string, any>>;

  // VAC
  getVAC(agentId: string): Promise<Record<string, any>>;

  // Trust Score
  getTrustScore(agentId: string): Promise<TrustScore>;

  // Attestations
  getAttestations(agentId: string, partnerType?: string): Promise<any[]>;

  // Chain Verification (requires API key)
  verifyChain(params: {
    receiptReference: string;
    chain: string;
    chainSpecific: Record<string, any>;
    transaction?: Record<string, any>;
  }): Promise<ChainVerification>;

  verifyLightningPayment(params: {
    receiptReference: string;
    paymentHash: string;
    preimage: string;
    presenterRole?: string;
    payeeAttestation?: Record<string, any>;
  }): Promise<ChainVerification>;

  verifyTronTransaction(params: {
    receiptReference: string;
    tronTxHash: string;
    network?: string;
  }): Promise<ChainVerification>;

  // Audit Trail
  getActivities(agentDid: string, options?: { limit?: number; since?: string }): Promise<any[]>;
  writeAuditEvent(params: {
    receiptReference: string;
    agentId: string;
    amount: string;
    currency: string;
    category: string;
    agentDid?: string;
    rail?: string;
    settlementTxHash?: string;
  }): Promise<AuditEvent>;

  // Extensions (requires API key)
  registerExtension(params: {
    extensionId: string;
    displayName: string;
    issuerDid: string;
    schema: Record<string, any>;
    issuerDisplayName?: string;
    issuerDomain?: string;
    summaryFields?: string[];
  }): Promise<Record<string, any>>;

  submitExtensionAttestation(params: {
    extensionId: string;
    credential: Record<string, any>;
    summaryFields?: string[];
  }): Promise<Record<string, any>>;

  // Counterparties
  getCounterparties(agentId: string, limit?: number): Promise<Record<string, any>>;
}

export default ObserverClient;
