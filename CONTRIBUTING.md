# Contributing to Observer Protocol

Thank you for your interest in contributing! This project is building the trust layer for the agentic economy, and we welcome contributors who understand that verifiable agent identity matters.

## How to Contribute

### Reporting Issues

- **Security issues:** Email security@observerprotocol.org (do not open public issues)
- **Bugs:** Open a GitHub issue with reproduction steps
- **Feature requests:** Open a GitHub issue with use case description

### Code Contributions

1. **Fork the repository**
2. **Create a feature branch:** `git checkout -b feature/your-feature-name`
3. **Make your changes** with clear commit messages
4. **Test your changes** (see Testing section below)
5. **Submit a pull request** with detailed description

### Development Setup

```bash
# Clone the repository
git clone https://github.com/observer-protocol/arp-spec.git
cd arp-spec

# For SDK development
cd sdk
npm install  # or pip install -e . for Python

# For API development (see api-server.py)
# Requires PostgreSQL, see database setup in docs/
```

### Testing

- All new features must include tests
- Run existing tests before submitting PR: `npm test` or `pytest`
- Integration tests should verify actual challenge-response flow

### Code Style

- **JavaScript/TypeScript:** Follow existing ESLint configuration
- **Python:** PEP 8 compliant
- **Documentation:** Clear, concise, with examples

### Commit Message Format

```
type: Brief description

Longer explanation if needed.

- Bullet points for details
- Reference issues: Fixes #123
```

Types:
- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `refactor:` Code refactoring
- `test:` Adding tests
- `chore:` Maintenance tasks

### Areas We Need Help

**High Priority:**
- Security audit and hardening (Phase 4)
- Additional cryptographic implementations (Ed25519 support)
- Performance optimization for high-volume attestation
- MCP server SDKs for more languages (Go, Rust)

**Medium Priority:**
- Documentation improvements
- Integration examples for popular frameworks
- Reputation algorithm research
- Sybil-resistance mechanisms

**Low Priority (but welcome):**
- UI/UX improvements for badge display
- Additional badge designs
- Translation of documentation

### Recognition

Contributors will be:
- Listed in CONTRIBUTORS.md
- Mentioned in release notes
- Credited in relevant documentation

### Questions?

- Open a GitHub discussion
- Email: hello@observerprotocol.org
- Nostr: Maxi is active there

## Code of Conduct

- Be respectful and constructive
- Focus on the problem, not the person
- Assume good intentions
- Help newcomers learn

We reserve the right to remove contributors who violate these principles.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
