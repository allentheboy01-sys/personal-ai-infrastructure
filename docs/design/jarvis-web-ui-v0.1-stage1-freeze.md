# Jarvis Web UI V0.1 — Stage 1 Freeze

## Status

FINAL FREEZE

2026-08-19

Human visual review and human brand review both passed.

## Product boundary

Stage 1 is a frontend-only static React implementation under
`apps/jarvis-web`. It uses deterministic synthetic mock data and contains only:

- primary navigation for Chat, Resources, and Providers;
- contextual Execution, Resource Detail, and Provider Detail work surfaces;
- unified Resource presentation for image, document, message, and generic
  Resources; and
- read-only Provider views for Gmail, Immich, and Nextcloud.

It contains no backend, API, database, Hermes or PDI integration, Resource
Access transport, production service, authentication system, or Provider
credential.

## Visual freeze

The frozen design language is **Calm Intelligence**:

- warm neutral visual foundation;
- restrained green accent;
- low-noise borders and calm information hierarchy;
- no large AI gradients, glow, or decorative sci-fi styling;
- one provider-independent Resource visual system;
- Provider provenance does not select a renderer;
- desktop and mobile remain one responsive design system; and
- the Work Panel is contextual rather than dashboard-first.

The static visual system is approved. V0.1 must not continue general visual or
logo exploration unless a later reviewed requirement invalidates this freeze.

## Jarvis identity freeze

The selected and frozen product mark is **A — Beacon / Guide**. Its geometry
expresses:

- a central intelligence core;
- an open guidance ring;
- a restrained directional cue;
- calm, premium, non-sci-fi product character; and
- compatibility with possible subtle active-state motion later.

The wordmark uses the existing UI typography. B — Quiet Orbit and C — Focus
Field remain rejected review alternatives, not active product marks.

## Frontend architecture

The implementation uses React, TypeScript, Vite, Tailwind CSS, Radix
primitives, Lucide icons, and limited Motion. Mock models and fixtures are kept
behind frontend boundaries so later HTTP clients can replace them without
introducing Provider-specific cards.

No production Node server, WebSocket, service worker, PWA, Redux, Python code,
PDI import, Provider endpoint, PostgreSQL URL, or PDI UDS path is part of Stage
1.

## Review evidence

Version-controlled review evidence includes:

- the seven deterministic desktop/mobile screenshots under
  `apps/jarvis-web/review/screenshots`;
- the final Stage 1.1 visual contact sheet;
- the three SVG identity candidate marks and specimens; and
- the final Stage 1.2 identity review sheet.

Generated dependency trees, Vite output, Playwright browser downloads, test
results, TypeScript build metadata, temporary font configuration, and the
user-local Node runtime are excluded from Git.

## Deferred scope

Backend, Jarvis state database, Hermes RuntimeAdapter, PDI consumer client,
Resource Access proxy, Memory, Tasks, Actions, Approval, Proactive behavior,
Add Provider, Marketplace, public authentication, PWA, push, and production
deployment remain deferred. Stage 2 implementation has not started.
