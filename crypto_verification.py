# Real Cryptographic Verification for Observer Protocol
# Using Python's built-in cryptography library (already installed)

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, encode_dss_signature
from cryptography.exceptions import InvalidSignature
import hashlib
import base58


def recover_public_key_from_signature(message: bytes, signature_hex: str) -> tuple:
    """
    Attempt to recover the public key from an ECDSA signature.
    
    For SECP256k1, there are 4 possible public keys that could produce a valid signature.
    We need to try all 4 recovery IDs (0-3) to find the correct one.
    
    Returns:
        tuple: (public_key_hex, recovery_id) if successful, (None, None) if failed
    """
    try:
        sig_bytes = bytes.fromhex(signature_hex)
        
        # Parse signature
        if len(sig_bytes) == 64:
            # Raw format: r || s (32 bytes each)
            r = int.from_bytes(sig_bytes[:32], 'big')
            s = int.from_bytes(sig_bytes[32:], 'big')
        elif 68 <= len(sig_bytes) <= 72:
            # DER format - decode it
            from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
            r, s = decode_dss_signature(sig_bytes)
        else:
            return None, None
        
        # Curve parameters for SECP256K1
        curve = ec.SECP256K1()
        n = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
        p = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
        
        # Message hash
        message_hash = int.from_bytes(hashlib.sha256(message).digest(), 'big')
        
        # Try all 4 recovery IDs
        for recovery_id in range(4):
            try:
                # This is a simplified recovery - full implementation requires
                # elliptic curve point operations that are complex to implement from scratch
                # For production, we'd use a library like coincurve or ecdsa
                
                # For now, we verify the signature components are valid
                if 1 <= r < n and 1 <= s < n:
                    # Components are valid, but we can't fully recover without more context
                    # Return a placeholder indicating we'd need the public key
                    return "recovery_requires_full_implementation", recovery_id
            except:
                continue
        
        return None, None
        
    except Exception as e:
        print(f"Recovery error: {e}")
        return None, None


def verify_signature_simple(message: bytes, signature_hex: str, public_key_hex: str) -> bool:
    """
    Verify an ECDSA signature (SECP256k1) against a message and public key.
    
    This is the actual cryptographic verification using the cryptography library.
    """
    try:
        # Decode signature
        sig_bytes = bytes.fromhex(signature_hex)
        
        # Decode public key
        public_key_bytes = bytes.fromhex(public_key_hex)
        
        # Load the public key
        if len(public_key_bytes) == 65 and public_key_bytes[0] == 0x04:
            # Uncompressed format: 04 || x || y (32 bytes each)
            public_numbers = ec.EllipticCurvePublicNumbers(
                x=int.from_bytes(public_key_bytes[1:33], 'big'),
                y=int.from_bytes(public_key_bytes[33:65], 'big'),
                curve=ec.SECP256K1()
            )
            public_key = public_numbers.public_key()
        elif len(public_key_bytes) == 33 and public_key_bytes[0] in (0x02, 0x03):
            # Compressed format: 02/03 || x (32 bytes) — decompress using curve math
            p = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
            x = int.from_bytes(public_key_bytes[1:], 'big')
            y_sq = (pow(x, 3, p) + 7) % p
            y = pow(y_sq, (p + 1) // 4, p)
            # Ensure parity matches prefix byte
            if (y & 1) != (public_key_bytes[0] & 1):
                y = p - y
            public_numbers = ec.EllipticCurvePublicNumbers(
                x=x,
                y=y,
                curve=ec.SECP256K1()
            )
            public_key = public_numbers.public_key()
        else:
            return False
        
        # Parse signature
        if len(sig_bytes) == 64:
            # Raw format: r || s - encode to DER
            r = int.from_bytes(sig_bytes[:32], 'big')
            s = int.from_bytes(sig_bytes[32:], 'big')
            signature_der = encode_dss_signature(r, s)
        elif 68 <= len(sig_bytes) <= 72:
            # Already DER format
            signature_der = sig_bytes
        else:
            return False
        
        # Verify the signature
        public_key.verify(
            signature_der,
            message,
            ec.ECDSA(hashes.SHA256())
        )
        
        return True
        
    except InvalidSignature:
        return False
    except Exception as e:
        print(f"Verification error: {e}")
        return False


# For the current implementation, we need to store the public key during registration
# and use it during verification. The database currently only stores the hash.

# Solution: Store the public key in a separate lookup table or field
# For now, we'll use a workaround: store the public key in memory during testing
# and implement proper storage in the next migration

_PUBLIC_KEY_CACHE = {}

def detect_key_type(public_key_hex: str) -> str:
    """
    Detect the type of public key based on its format.
    
    SECP256k1 keys are 33 bytes (compressed) or 65 bytes (uncompressed)
    Ed25519 keys are 32 bytes
    
    Args:
        public_key_hex: The public key in hex format
        
    Returns:
        str: 'secp256k1', 'ed25519', or 'unknown'
    """
    try:
        # Remove '0x' prefix if present
        if public_key_hex.startswith('0x'):
            public_key_hex = public_key_hex[2:]
        
        public_key_bytes = bytes.fromhex(public_key_hex)
        key_len = len(public_key_bytes)
        
        # SECP256k1 compressed: 33 bytes starting with 0x02 or 0x03
        if key_len == 33 and public_key_bytes[0] in (0x02, 0x03):
            return 'secp256k1'
        
        # SECP256k1 uncompressed: 65 bytes starting with 0x04
        if key_len == 65 and public_key_bytes[0] == 0x04:
            return 'secp256k1'
        
        # Ed25519: 32 bytes (raw)
        if key_len == 32:
            return 'ed25519'
        
        return 'unknown'
    except Exception:
        return 'unknown'


def verify_ed25519_signature(message_bytes: bytes, signature_hex: str, public_key_hex: str) -> bool:
    """
    Verify an Ed25519 signature against a message and public key.
    
    Used for Solana and other Ed25519-based blockchain agents.
    
    Args:
        message_bytes: The original message that was signed (bytes)
        signature_hex: The signature in hex format (64 bytes)
        public_key_hex: The public key in hex format (32 bytes) OR base58-encoded Solana address
    
    Returns:
        bool: True if signature is valid, False otherwise
    """
    try:
        # Remove '0x' prefix if present
        if public_key_hex.startswith('0x'):
            public_key_hex = public_key_hex[2:]
        if signature_hex.startswith('0x'):
            signature_hex = signature_hex[2:]
        
        # Try to decode public key - could be hex or base58 (Solana address)
        public_key_bytes = None
        try:
            # Try hex first
            public_key_bytes = bytes.fromhex(public_key_hex)
            if len(public_key_bytes) != 32:
                # If not 32 bytes, might be base58 encoded
                raise ValueError("Not 32 bytes")
        except ValueError:
            # Try base58 decoding (for Solana addresses)
            try:
                public_key_bytes = base58.b58decode(public_key_hex)
                if len(public_key_bytes) != 32:
                    print(f"Ed25519 verification error: Invalid public key length {len(public_key_bytes)}")
                    return False
            except Exception:
                print(f"Ed25519 verification error: Could not decode public key")
                return False
        
        # Decode signature (64 bytes for Ed25519)
        sig_bytes = bytes.fromhex(signature_hex)
        if len(sig_bytes) != 64:
            print(f"Ed25519 verification error: Invalid signature length {len(sig_bytes)}")
            return False
        
        # Load the Ed25519 public key
        public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
        
        # Verify the signature
        public_key.verify(sig_bytes, message_bytes)
        
        return True
        
    except InvalidSignature:
        return False
    except Exception as e:
        print(f"Ed25519 verification error: {e}")
        return False


def verify_signature(message_bytes: bytes, signature_hex: str, public_key_hex: str) -> bool:
    """
    Verify a signature using the appropriate algorithm based on key type.
    
    Automatically detects whether the public key is SECP256k1 or Ed25519
    and routes to the correct verification function.
    
    Args:
        message_bytes: The original message that was signed (bytes)
        signature_hex: The signature in hex format
        public_key_hex: The public key in hex format (or base58 for Solana)
    
    Returns:
        bool: True if signature is valid, False otherwise
    """
    key_type = detect_key_type(public_key_hex)
    
    if key_type == 'ed25519':
        return verify_ed25519_signature(message_bytes, signature_hex, public_key_hex)
    elif key_type == 'secp256k1':
        return verify_signature_simple(message_bytes, signature_hex, public_key_hex)
    else:
        # Try Ed25519 as fallback (handles base58 Solana addresses which we can't detect length-wise)
        result = verify_ed25519_signature(message_bytes, signature_hex, public_key_hex)
        if result:
            return True
        # If that fails, try SECP256k1
        return verify_signature_simple(message_bytes, signature_hex, public_key_hex)


def cache_public_key(agent_id: str, public_key_hex: str):
    """
    Cache the public key and its type for an agent.
    
    Stores both the key and detected type to avoid re-detection on every verification.
    """
    key_type = detect_key_type(public_key_hex)
    _PUBLIC_KEY_CACHE[agent_id] = {
        'public_key': public_key_hex,
        'key_type': key_type
    }

def get_cached_public_key(agent_id: str) -> str:
    """Get cached public key (returns just the key string)."""
    cached = _PUBLIC_KEY_CACHE.get(agent_id)
    if cached and isinstance(cached, dict):
        return cached.get('public_key')
    # Legacy support: plain string
    return cached

def get_cached_key_type(agent_id: str) -> str:
    """Get cached key type for an agent."""
    cached = _PUBLIC_KEY_CACHE.get(agent_id)
    if cached and isinstance(cached, dict):
        return cached.get('key_type', 'unknown')
    # Legacy support: try to detect from string
    if cached and isinstance(cached, str):
        return detect_key_type(cached)
    return 'unknown'
