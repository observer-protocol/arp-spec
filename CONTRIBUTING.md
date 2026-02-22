# Contributing to Observer Protocol

Thank you for your interest in contributing. This is an open protocol — it improves through community participation.

## What We're Looking For

- **Protocol feedback** — edge cases, ambiguities, or gaps in the ARP spec
- **Reference implementations** — ARP servers or clients in any language
- **Protocol validators** — verification modules for BSV, x402, Fedimint, Ark, and other rails
- **Documentation improvements** — especially translations (Spanish is highest priority)
- **Real-world test data** — verified ARP events from autonomous agents

## How to Contribute

### Spec Changes (ARP-SPEC.md / schema.json)

1. Open an issue first describing the proposed change and rationale
2. Allow 7 days for community discussion on draft changes
3. Submit a PR with the change, updated schema.json, and changelog entry
4. Breaking changes require a version bump and migration guide

### Bug Reports

Open an issue with:
- ARP spec version
- Event type affected
- Expected vs. actual behavior
- Minimal reproducible example (JSON)

### New Protocol Validators

To add a new protocol to the registry:

1. Open a PR adding the protocol value to `schema.json` enum
2. Include verification method description in `ARP-SPEC.md` §5
3. Link to at least one real-world implementation that uses this protocol

### Translations

Documentation translations go in `docs/{language_code}/`. Spanish (`docs/es/`) is the first priority. If you speak Spanish and want to help, open an issue.

## Code of Conduct

- Be direct and technical
- Criticism of ideas is welcome; personal attacks are not
- Counter-evidence is valued, not suppressed — if data challenges the design, say so
- No affiliation requirements: BSV, x402, and Lightning contributors are equally welcome

## License

By contributing, you agree your contributions are licensed under MIT (code) and CC BY 4.0 (documentation and spec).
