# PDI Documentation

Start with the [repository README](../README.md). It explains the product,
current Provider support, consumer boundaries, maturity, and development entry
point. PDI is the product; Jarvis documentation is secondary reference-consumer
material.

## Getting started

- [Product overview and self-host quick start](../README.md)
- [Manual self-host installation](getting-started/self-host.md)
- [Clean-clone portability acceptance](getting-started/clean-clone-acceptance.md)
- [Local development and test isolation](development/local-development.md)
- [Deployment boundary and portable reference assets](deployment/README.md)

The self-host guide requires PostgreSQL and one Provider, but not Jarvis,
Docker, Tailscale, or multiple Provider accounts.

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

- [Nextcloud Adapter](../src/pdi/adapters/nextcloud/adapter.py)
- [Immich Adapter](../src/pdi/adapters/immich/adapter.py)
- [Immich discovery notes](discovery/immich.md)
- [Gmail Provider V0.1](design/pdi-gmail-provider-v0.1.md)
- [Gmail Adapter](../src/pdi/adapters/gmail/adapter.py)

Provider-independent contracts come from the architecture, not from any one
Provider API.

## Consumer interfaces / MCP

- [Personal retrieval read boundary](design/personal-retrieval-read-v0.1.md)
- [PDI Query V0.2](design/pdi-query-v0.2.md)
- [Unified bounded Resource query V0.1](design/pdi-unified-resource-query-v0.1.md)
- [Bounded Resource image preview V0.1](design/pdi-resource-image-preview-v0.1.md)
- [Data Status V0.1](design/pdi-data-status-v0.1.md)
- [Read-only MCP composition](../src/pdi_mcp/)
- [Bounded Resource Access process](../src/pdi_resource_access/)

Consumers use these public boundaries and do not access PDI persistence or
Provider credentials directly.

## Security and privacy

- [Security policy](../SECURITY.md)
- [Private operations boundary](security/private-operations-boundary.md)
- [Database migration and test isolation](database-migrations.md)

## Deployment

- [Deployment boundary and reference assets](deployment/README.md)

Network topology and service-management choices are deployment-specific; PDI
does not require Tailscale or another particular exposure mechanism.

## Development

- [Local development](development/local-development.md)
- [Dependency reproducibility](development/dependencies.md)
- [Continuous integration](development/continuous-integration.md)
- [Public release process](development/release-process.md)
- [Contribution guide](../CONTRIBUTING.md)
- [Repository automation and contributor rules](../AGENTS.md)
- [ADR guidelines](adr/000-adr-guidelines.md)

## Project status and records

- [Roadmap](roadmap/ROADMAP.md)
- [Contributor-facing current context](context/CURRENT_CONTEXT.md)
- [PDI v0.4 tagged release](releases/v0.4.md)
- [PDI v0.5 tagged release](releases/v0.5.md)
- [PDI v0.6.0](releases/v0.6.0.md)
- [Archived v0.6 engineering milestone evidence](archive/pdi/v0.6-engineering-milestone.md)

The current context is an implementation snapshot for contributors, not the
public product introduction. Package metadata and the release note identify
`v0.6.0`; the exact annotated Git tag on a source commit determines whether
that commit is the public release.

## Reference consumers

Jarvis validates that an AI runtime can consume PDI without owning PDI state.
It is optional, replaceable, and not the canonical PDI UI.

- [Jarvis runtime integration](design/jarvis-runtime-integration-v0.1.md)
- [Jarvis Resource presentation](design/jarvis-web-resource-result-presentation-v0.1.1.md)
- [Jarvis Web/Search boundary](design/jarvis-web-search-capability-v0.1.md)
- [Jarvis historical index](archive/jarvis/README.md)

## Design records

Current PDI designs live in `design/`; architecture decisions live in `adr/`.
Jarvis-specific designs are reference-consumer records and do not define PDI
Core.

## Archive

- [Jarvis historical Stage/Gate index](archive/jarvis/README.md)
- [PDI v0.6 engineering milestone evidence](archive/pdi/v0.6-engineering-milestone.md)

Archive records preserve engineering history. They are not the current PDI
architecture, status, or installation guide.
