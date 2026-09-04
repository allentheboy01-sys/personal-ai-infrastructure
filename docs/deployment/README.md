# Deployment boundary

PDI Core requires Python 3.13, PostgreSQL, and configuration for the Providers
a deployment chooses to enable. It does not require a specific hostname,
filesystem layout, service manager, container runtime, private-network product,
or AI runtime.

Start with the [manual self-host guide](../getting-started/self-host.md).

## Public reference layout

The tracked systemd and launcher examples use one conventional Linux layout:

| Concern | Reference value |
| --- | --- |
| Service account | `pdi` |
| Application root and virtual environment | `/opt/pdi`, `/opt/pdi/.venv` |
| Protected configuration | `/etc/pdi/pdi.env` |
| Runtime state | external PostgreSQL |
| Resource Access transport | AF_UNIX under `/run/pdi/` |

These values make the examples coherent; they are deployment choices, not PDI
Core contracts. A different layout works for manual commands when its paths and
service definitions are updated consistently.

## Repository assets

- `deployment/pdi.env.example` contains the required database group and
  optional, independent Provider groups.
- `deployment/examples/postgres/` is a PostgreSQL 16 reference bound to
  loopback by default. Existing PostgreSQL is equally supported.
- `deployment/mcp/pdi-mcp` is a protected stdio MCP launcher; it opens no
  network listener.
- `deployment/systemd/pdi-*.service` and `.timer` files retain oneshot formal
  pipelines, journald output, the global operational lock, bounded timeouts,
  and persistent example schedules.
- `deployment/resource-access/` demonstrates the optional bounded AF_UNIX
  Resource Access service.
- `deployment/jarvis/` and Jarvis-named units are optional reference-consumer
  assets, not PDI installation requirements.

Install only the units for configured capabilities. Review schedules before
enabling timers. Gmail remains explicit/manual and intentionally has no public
timer.

## Provider composition

Database configuration is required for persistence. Provider configuration is
optional globally and required only when that Provider is selected:

- `pdi sync --provider nextcloud` requires only database and Nextcloud groups;
- `pdi sync --provider immich` requires only database and Immich groups;
- `pdi sync --provider gmail` requires only database and the existing Gmail
  manual-pilot authentication state; and
- `pdi sync` implicitly includes configured Nextcloud and Immich Providers,
  never Gmail, and fails if no eligible Provider is configured.

The sync operation defaults to `full`; `--operation full` is an equivalent
explicit spelling. `incremental`, `bootstrap`, and `recover` are supported only
with an explicit Nextcloud or Immich `--provider`. Gmail rejects those
operations. Direct `pdi sync` execution remains a manual/debug surface without
the formal lock or PipelineRun ledger. Formal unattended full, incremental,
bootstrap, and recovery operations use `pdi.operational`.

The existing daily full timers remain unchanged: Nextcloud at 02:15 and Immich
at 05:15. Optional reference incremental timers run at staggered approximately
five-minute offsets and use a 300-second lock timeout. Do not enable either
incremental timer before its explicit formal bootstrap succeeds. A
reconciliation latch requires the corresponding explicit formal recovery;
timers never bootstrap or recover automatically.

MCP needs only the database. Immich configuration optionally enables semantic
retrieval and bounded image-preview Resource access. Without Immich
configuration, the image-preview Tool remains registered and returns a stable
capability-unavailable result when invoked. Nextcloud and Gmail credentials are
not MCP requirements.

## Core versus deployment choices

PDI Core invariants include Provider isolation, stable identity, public
application-service/MCP boundaries, bounded Resource Access, secret handling,
and production/test separation.

systemd, Docker, loopback listeners, private overlay networks, exact ports, and
scheduling are deployment choices. The reference defaults are conservative,
but every operator remains responsible for credentials, backups, Provider
permissions, network exposure, and timer cadence.
