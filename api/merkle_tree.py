"""
Merkle tree utilities for Spec 3.4 audit batching.

Agents batch activities into per-window Merkle trees and sign only the root.
Individual activities are provable via standard Merkle inclusion proofs.

Tree construction:
  - Leaves are SHA-256 hashes of canonicalized JSON (RFC 8785 / JCS).
  - Binary tree: if odd number of leaves, duplicate the last leaf.
  - Internal nodes: SHA-256(left || right).

Proof format:
  - proofPath: array of sibling hashes, leaf-to-root order.
  - Each entry includes the sibling hash and its position ('left' or 'right').
"""

import hashlib
import json
import math
from typing import Optional


def canonical_json_bytes(obj: dict) -> bytes:
    """
    Canonicalize a dict to bytes per JCS (RFC 8785).
    Same canonicalization as crypto_utils.canonical_bytes but without
    proof-stripping — this is for leaf hashing, not signature verification.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def leaf_hash(entry: dict) -> str:
    """
    Compute the SHA-256 hash of a canonicalized audit entry.
    Returns hex-encoded hash string.
    """
    return hashlib.sha256(canonical_json_bytes(entry)).hexdigest()


def _hash_pair(left: str, right: str) -> str:
    """Hash two hex-encoded hashes together: SHA-256(left_bytes || right_bytes)."""
    combined = bytes.fromhex(left) + bytes.fromhex(right)
    return hashlib.sha256(combined).hexdigest()


def build_tree(leaf_hashes: list[str]) -> tuple[str, list[list[str]]]:
    """
    Build a Merkle tree from a list of leaf hashes.

    Args:
        leaf_hashes: List of hex-encoded SHA-256 hashes.

    Returns:
        (root_hash, levels) where levels[0] = leaves, levels[-1] = [root].

    Raises:
        ValueError: If leaf_hashes is empty.
    """
    if not leaf_hashes:
        raise ValueError("Cannot build Merkle tree from empty leaf list")

    if len(leaf_hashes) == 1:
        return leaf_hashes[0], [leaf_hashes]

    levels = [list(leaf_hashes)]

    current = list(leaf_hashes)
    while len(current) > 1:
        # If odd, duplicate last
        if len(current) % 2 == 1:
            current.append(current[-1])

        next_level = []
        for i in range(0, len(current), 2):
            next_level.append(_hash_pair(current[i], current[i + 1]))

        levels.append(next_level)
        current = next_level

    return current[0], levels


def generate_proof(leaf_hashes: list[str], leaf_index: int) -> list[dict]:
    """
    Generate a Merkle inclusion proof for a leaf at the given index.

    Args:
        leaf_hashes: All leaf hashes in the tree.
        leaf_index: Index of the leaf to prove.

    Returns:
        List of proof steps, each: {"hash": "<hex>", "position": "left"|"right"}.
        The position indicates where the sibling sits relative to the current node.

    Raises:
        IndexError: If leaf_index is out of range.
    """
    if leaf_index < 0 or leaf_index >= len(leaf_hashes):
        raise IndexError(f"Leaf index {leaf_index} out of range [0, {len(leaf_hashes)})")

    _, levels = build_tree(leaf_hashes)
    proof = []
    idx = leaf_index

    for level in levels[:-1]:  # skip the root level
        # Pad if odd
        padded = list(level)
        if len(padded) % 2 == 1:
            padded.append(padded[-1])

        if idx % 2 == 0:
            sibling_idx = idx + 1
            proof.append({"hash": padded[sibling_idx], "position": "right"})
        else:
            sibling_idx = idx - 1
            proof.append({"hash": padded[sibling_idx], "position": "left"})

        idx = idx // 2

    return proof


def verify_proof(leaf_hash_hex: str, proof_path: list[dict], expected_root: str) -> bool:
    """
    Verify a Merkle inclusion proof.

    Args:
        leaf_hash_hex: Hex-encoded SHA-256 of the leaf.
        proof_path: List of {"hash": "<hex>", "position": "left"|"right"}.
        expected_root: The expected root hash.

    Returns:
        True if the proof reconstructs the expected root.
    """
    current = leaf_hash_hex

    for step in proof_path:
        sibling = step["hash"]
        if step["position"] == "left":
            current = _hash_pair(sibling, current)
        else:
            current = _hash_pair(current, sibling)

    return current == expected_root


def compute_root(leaf_hashes: list[str]) -> str:
    """Convenience: compute just the root hash from leaf hashes."""
    root, _ = build_tree(leaf_hashes)
    return root
