"""
DID Document Generator for Observer Protocol

Generates W3C-compliant DID documents with CAIP-10 account references
for cross-chain identity awareness.
"""

import json
from typing import Any
from datetime import datetime, timezone

# CAIP-10 chain ID registry
CAIP2_CHAIN_IDS = {
    "tron": "tron:mainnet",
    "trc20": "tron:mainnet",
    "solana": "solana:mainnet",
}

SERVICE_TYPE_PAYMENT_RAIL = "PaymentRail"
SERVICE_TYPE_LIGHTNING = "LightningEndpoint"
SERVICE_TYPE_HTTP_402 = "HTTP402Endpoint"


def build_did_document(
    *,
    did: str,
    public_key: str,
    public_key_type: str = "Ed25519",
    rails: list[str],
    wallet_addresses: dict[str, str],
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build a W3C DID document for an agent."""
    if created_at is None:
        created_at = datetime.now(timezone.utc).isoformat()

    key_id = f"{did}#key-1"

    vm_type_map = {
        "Ed25519": "Ed25519VerificationKey2020",
        "Secp256k1": "EcdsaSecp256k1VerificationKey2019",
    }
    vm_type = vm_type_map.get(public_key_type, "Ed25519VerificationKey2020")

    doc: dict[str, Any] = {
        "@context": [
            "https://www.w3.org/ns/did/v1",
            "https://w3id.org/security/suites/ed25519-2020/v1",
        ],
        "id": did,
        "verificationMethod": [
            {
                "id": key_id,
                "type": vm_type,
                "controller": did,
                "publicKeyMultibase": public_key
                if public_key.startswith("z")
                else f"z{public_key}",
            }
        ],
        "authentication": [key_id],
        "assertionMethod": [key_id],
        "service": _build_services(did, rails, wallet_addresses),
        "created": created_at,
    }

    if public_key_type == "Secp256k1":
        doc["@context"] = [
            "https://www.w3.org/ns/did/v1",
            "https://w3id.org/security/suites/secp256k1-2019/v1",
        ]

    return doc


def _build_services(
    did: str, rails: list[str], wallet_addresses: dict[str, str]
) -> list[dict[str, Any]]:
    """Build the service endpoints section with CAIP-10 references."""
    services: list[dict[str, Any]] = []

    # TRON (covers both 'tron' and 'trc20' rails)
    tron_rails_present = [r for r in rails if r in {"tron", "trc20"}]
    if tron_rails_present and "tron" in wallet_addresses:
        tron_addr = wallet_addresses["tron"]
        services.append(
            {
                "id": f"{did}#tron",
                "type": SERVICE_TYPE_PAYMENT_RAIL,
                "serviceEndpoint": {
                    "rail": "tron",
                    "rails": tron_rails_present,
                    "network": "tron-mainnet",
                    "address": tron_addr,
                    "caip10": f"{CAIP2_CHAIN_IDS['tron']}:{tron_addr}",
                    "supports": (
                        ["TRX", "USDT-TRC20"] if "trc20" in tron_rails_present else ["TRX"]
                    ),
                },
            }
        )

    # Solana
    if "solana" in rails and "solana" in wallet_addresses:
        sol_addr = wallet_addresses["solana"]
        services.append(
            {
                "id": f"{did}#solana",
                "type": SERVICE_TYPE_PAYMENT_RAIL,
                "serviceEndpoint": {
                    "rail": "solana",
                    "network": "solana-mainnet",
                    "address": sol_addr,
                    "caip10": f"{CAIP2_CHAIN_IDS['solana']}:{sol_addr}",
                    "supports": ["SOL", "SPL"],
                },
            }
        )

    # Lightning
    if "lightning" in rails and "lightning" in wallet_addresses:
        ln_addr = wallet_addresses["lightning"]
        services.append(
            {
                "id": f"{did}#lightning",
                "type": SERVICE_TYPE_LIGHTNING,
                "serviceEndpoint": {
                    "rail": "lightning",
                    "network": "bitcoin-mainnet",
                    "endpoint": ln_addr,
                    "supports": ["BTC"],
                },
            }
        )

    # L402
    if "l402" in rails:
        services.append(
            {
                "id": f"{did}#l402",
                "type": SERVICE_TYPE_HTTP_402,
                "serviceEndpoint": {
                    "rail": "l402",
                    "protocol": "L402",
                    "endpoint": wallet_addresses.get("l402"),
                },
            }
        )

    # x402
    if "x402" in rails:
        services.append(
            {
                "id": f"{did}#x402",
                "type": SERVICE_TYPE_HTTP_402,
                "serviceEndpoint": {
                    "rail": "x402",
                    "protocol": "x402",
                    "endpoint": wallet_addresses.get("x402"),
                },
            }
        )

    return services


def render_did_document_json(
    *,
    did: str,
    public_key: str,
    public_key_type: str = "Ed25519",
    rails: list[str],
    wallet_addresses: dict[str, str],
    created_at: str | None = None,
) -> str:
    """Return the DID document as a JSON string."""
    doc = build_did_document(
        did=did,
        public_key=public_key,
        public_key_type=public_key_type,
        rails=rails,
        wallet_addresses=wallet_addresses,
        created_at=created_at,
    )
    return json.dumps(doc, indent=2)
