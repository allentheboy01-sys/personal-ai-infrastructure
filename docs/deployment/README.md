# Deployment boundary

PDI Core requires Python, PostgreSQL, and configuration for the Providers a
deployment chooses to enable. It does not require a specific username,
hostname, filesystem path, service manager, container layout, private-network
product, or AI runtime.

## Current repository assets

The files under `deployment/` were derived from a validated self-hosted system.
They demonstrate service separation, protected configuration, scheduling, and
bounded Resource Access, but still contain installation-specific paths and
users. They are reference assets, not a portable installer and not universal
defaults.

Do not install them unchanged on another host. Review and parameterize at least:

- runtime user and group;
- checkout and virtual-environment paths;
- protected configuration and credential locations;
- PostgreSQL and Provider endpoints;
- socket paths, ports, and service dependencies; and
- timer cadence and private-network exposure.

Public Readiness Phase D will define the portable deployment contract and
replace author-derived assumptions with documented variables. This Phase A+B
boundary change does not alter any unit, launcher, runtime setting, or installed
service behavior.

## Core versus deployment choices

PDI Core invariants include Provider isolation, stable identity, public
application-service/MCP boundaries, bounded Resource Access, secret handling,
and production/test separation.

systemd, containers, loopback listeners, private overlay networks, exact ports,
and scheduling are deployment choices. Public examples may recommend them, but
PDI must remain independently installable without adopting one person's host
topology.
