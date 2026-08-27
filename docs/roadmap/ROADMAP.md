# PDI Roadmap

The roadmap records product delivery order. Architecture and current contracts
live in their dedicated documents; operational validation chronology belongs in
release or archived reference records.

PDI is the product. Consumer runtimes are optional integrations over stable
public boundaries and do not define PDI Core.

## Completed milestones

- **v0.1 — Write Pipeline MVP:** Provider-independent identity decisions and
  persistence.
- **v0.2 — Multi-provider Sync MVP:** incremental, idempotent Nextcloud and
  Immich synchronization.
- **v0.3 — Read Pipeline MVP:** stable query services and immutable Resource
  read models.
- **v0.4 — Jarvis Tool Execution MVP:** the first validated reference-consumer
  integration over PDI; Jarvis remains optional.
- **v0.5 — Personal Retrieval Runtime:** Resource projection, deterministic
  observations, structured/Provider/rich retrieval, bounded representations,
  and read-only MCP.

Git tags and package metadata currently stop at `v0.5.0` / `0.5.0`.

## Current — pre-1.0 public readiness

The untagged **v0.6 engineering milestone** adds operational hardening, typed
Resources, bounded Data Status, minimal Person identity, one explicit
Provider-derived `Resource depicts Person` relation, and the limited/manual
Gmail Provider. Its release document records validation history; it is not a
tagged public package release.

Public Readiness Phases A-C establish:

- privacy and private-operations boundaries;
- PDI-first repository identity and Jarvis reference-consumer positioning;
- a public product README, Provider maturity matrix, consumer-interface map,
  and honest pre-1.0 status; and
- host-neutral contributor documentation and navigation.

## Next public-readiness work

- **Phase D — Portability:** make Provider configuration, commands, and
  deployment examples usable outside the original installation.
- **Phase E — OSS hygiene and verification:** align version/package metadata,
  add reviewed CI and secret scanning, and validate a clean public install path.

## Future product work

- Stabilize proven Provider, observation, retrieval, access, and consumer
  contracts toward **v1.0 — Stable Personal Digital Infrastructure**.
- Evaluate additional Provider and consumer integrations independently, without
  making PDI Core depend on one AI runtime.
- Consider broader relationship retrieval, Provider-derived media relations,
  and user-controlled memory only after separate architecture review.
- Define explicit permission and write/action boundaries before introducing any
  write-capable consumer Tool.
- Review whether the optional Jarvis reference implementation should move to a
  separate repository once the public PDI package boundary is stable.

Future milestones are directional and subject to architecture review.
