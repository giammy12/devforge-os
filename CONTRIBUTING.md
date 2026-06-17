# Contributing to DevForge OS

Thank you for your interest in contributing! This document explains how to get started.

## Getting Started

1. Fork the repository on GitHub
2. Clone your fork locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/devforge-os.git
   cd devforge-os
   bash scripts/setup-dev-environment.sh
   ```
3. Create a branch for your work:
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Commit Convention

All commits must follow this format:
```
[FASE-X] Short description of what was done
```

Examples:
- `[FASE-1] Add web_frontend profile JSON`
- `[FASE-3] Implement Monaco Editor dark theme`
- `[FASE-4] Fix ROCm detection in LLM manager`

## Code Style

- Follow `.editorconfig` settings (enforced automatically by most editors)
- Python: follow PEP 8, max line length 88 (Black formatter)
- TypeScript: follow the ESLint config in `forge-ide/`
- C: K&R style, 4-space indent
- All comments in Italian for core components, English for public-facing docs

## Pull Requests

- One feature or fix per PR
- Include a description of what changed and why
- PRs against `main` only — no force pushes to main

## Reporting Issues

Open an issue on GitHub. Include:
- What you were doing
- What you expected
- What happened instead
- OS version and hardware (especially GPU model for AI issues)

## License

By contributing, you agree that your contributions will be licensed under GPL-3.0.
