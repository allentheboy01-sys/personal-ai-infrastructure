# PDI Roadmap

The roadmap records delivery order. Architecture and current implementation
details live in their dedicated documents.

## Completed

- **v0.1 — Write Pipeline MVP:** Established the provider-independent path
  from ProviderFact through identity decisions to persistence.
- **v0.2 — Multi-provider Sync MVP:** Connected Nextcloud and Immich through
  the same incremental and idempotent PDI Core.
- **v0.3 — Read Pipeline MVP:** Added stable query services and immutable Read
  Models for listing and retrieving assets.
- **v0.4 — Jarvis Tool Execution MVP:** Added the first consumer execution
  boundary with `list_assets` and `get_asset` Tools.

## Current

- **v0.5 — Jarvis HTTP API:** Define and implement the first external
  transport over the existing Tool Execution boundary.

## Future

- **v0.6 — Content Access:** Define bounded, safe access to asset content.
- **v0.7 — Retrieval:** Explore search and relationships only after their
  architecture is explicitly frozen.
- **v1.0 — Stable Personal Digital Infrastructure:** Stabilize the proven
  provider, write, read, and consumer contracts for long-term use.

Future milestones are directional and remain subject to architecture review.
