# Jarvis Web UI V0.1 — Stage 1 Static Frontend

## Frozen result

Jarvis Web UI V0.1 Stage 1 is frozen as a high-fidelity, responsive static
React frontend using deterministic synthetic data only. Human visual review
and brand review passed. The selected identity is A — Beacon / Guide and the
design language is Calm Intelligence.

The frozen surfaces are Chat, Resources, Providers, Execution, Resource
Detail, and Provider Detail. Resource rendering remains provider-independent;
Provider is provenance.

## Validation

The freeze passed TypeScript typecheck, ESLint, 14 Vitest component tests, 11
applicable Playwright tests across desktop/mobile projects, production Vite
build, and `git diff --check`. Nine Playwright cases were intentionally skipped
by their opposite-device project guards. A clean lockfile install succeeded and
`npm audit` reported zero known vulnerabilities after the bounded Vite 6.4.3
and Vitest 3.2.7 security updates.

## Boundary

This freeze adds no backend, API, Jarvis database, Hermes integration, PDI
integration, Resource Access integration, systemd or Tailscale configuration,
production service, Provider credential, or real personal data. Stage 2 has
not started.

The full visual and identity decisions are recorded in
`docs/design/jarvis-web-ui-v0.1-stage1-freeze.md`.
