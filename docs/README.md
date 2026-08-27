# PDI Documentation

PDI is the product in this repository. Jarvis is an optional reference
consumer. Documentation is organized so understanding PDI does not require
reading Jarvis Stage/Gate history or one author's server operations.

## Getting started

- [Repository README](../README.md)
- [Local development](development/local-development.md)
- [Current public context](context/CURRENT_CONTEXT.md)

The final end-user Quick Start is deferred to Public Readiness Phase C/D.

## Architecture

- [Current system architecture](../ARCHITECTURE.md)
- [Architecture overview](architecture/01-overview.md)
- [Provider](architecture/02-provider.md)
- [Provider Adapter](architecture/03-provider-adapter.md)
- [ProviderFact](architecture/04-provider-fact.md)
- [Sync Engine](architecture/05-sync-engine.md)
- [Identity](architecture/06-identity.md)
- [Decision](architecture/07-decision.md)
- [Repository](architecture/08-repository.md)
- [World Model](architecture/09-world-model.md)
- [Capability](architecture/10-capability.md)
- [Sync lifecycle](architecture/11-sync-lifecycle.md)

## Providers

- [Gmail Provider V0.1](design/pdi-gmail-provider-v0.1.md)
- [Immich discovery notes](discovery/immich.md)
- Provider-independent contracts are defined by the architecture documents,
  not by any one Provider implementation.

## Consumer interfaces / MCP

- [Personal retrieval read boundary](design/personal-retrieval-read-v0.1.md)
- [PDI Query V0.2](design/pdi-query-v0.2.md)
- [Data Status V0.1](design/pdi-data-status-v0.1.md)
- `src/pdi_mcp` composes the read-only consumer surface.
- `src/pdi_resource_access` exposes bounded Resource representations.

## Security and privacy

- [Security policy](../SECURITY.md)
- [Private operations boundary](security/private-operations-boundary.md)
- [Database migration and test isolation](database-migrations.md)

## Deployment

- [Deployment boundary and reference assets](deployment/README.md)

Current deployment files are derived from one installation and are not yet a
portable installer. Parameterization belongs to Public Readiness Phase D.

## Development

- [Local development](development/local-development.md)
- [Repository rules](../AGENTS.md)
- [ADR guidelines](adr/000-adr-guidelines.md)

## Reference consumers

Jarvis validates that an AI runtime can consume PDI without owning PDI state.
It is optional and replaceable.

- [Jarvis runtime integration](design/jarvis-runtime-integration-v0.1.md)
- [Jarvis Resource presentation](design/jarvis-web-resource-result-presentation-v0.1.1.md)
- [Jarvis Web/Search boundary](design/jarvis-web-search-capability-v0.1.md)
- [Jarvis historical index](archive/jarvis/README.md)

## Design records

Current PDI designs live in `design/`; architecture decisions live in `adr/`.
Jarvis-specific designs are reference-consumer records and do not define PDI
Core.

## Release notes

- [PDI v0.4](releases/v0.4.md)
- [PDI v0.5](releases/v0.5.md)
- [PDI v0.6](releases/v0.6.md)
- [Roadmap](roadmap/ROADMAP.md)

## Archive

- [Jarvis historical Stage/Gate index](archive/jarvis/README.md)

Archive records preserve engineering history. They are not the current PDI
architecture or installation guide.
