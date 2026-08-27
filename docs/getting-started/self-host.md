# Self-host PDI

This guide is the manual reference path for a technically competent Linux
operator. It installs PDI Core without Jarvis, without a public network
listener, and with exactly one Provider. It is intentionally not a one-click
installer.

## What you need

- Linux with Python 3.13 and Git;
- PostgreSQL 16, either existing or the repository's optional
  [Docker Compose reference](../../deployment/examples/postgres/README.md);
- a dedicated database and strong database password; and
- credentials for one Provider.

Nextcloud is used below because its WebDAV configuration is the simplest
end-to-end example. Immich can be configured independently. Gmail remains an
explicit manual pilot and is not part of implicit synchronization.

## 1. Create the service account and checkout

The public systemd reference uses the account `pdi`, application root
`/opt/pdi`, and protected configuration `/etc/pdi/pdi.env`.

```bash
sudo useradd --system --create-home --home-dir /var/lib/pdi \
  --shell /usr/sbin/nologin pdi
sudo install -d -o pdi -g pdi -m 0755 /opt/pdi
sudo -u pdi git clone <repository-url> /opt/pdi
sudo -u pdi python3.13 -m venv /opt/pdi/.venv
sudo -u pdi /opt/pdi/.venv/bin/python -m pip install --upgrade pip
sudo -u pdi /opt/pdi/.venv/bin/python -m pip install \
  -c /opt/pdi/constraints/python3.13.txt -e /opt/pdi
/opt/pdi/.venv/bin/python -m pip check
```

Replace `<repository-url>` with the repository URL you intend to use. An
existing checkout in another layout also works for manual commands; `/opt/pdi`
is the stable path used by the reference units, not a PDI Core requirement.

## 2. Prepare PostgreSQL

Use an existing PostgreSQL 16 service, or start the loopback-only reference:

```bash
cd /opt/pdi/deployment/examples/postgres
cp .env.example .env
# Edit .env and replace the synthetic password before starting PostgreSQL.
docker compose up -d
```

The reference publishes PostgreSQL only on `127.0.0.1:5432`. Docker is not
required when an existing PostgreSQL instance is available.

## 3. Configure persistence and one Provider

```bash
sudo install -d -o pdi -g pdi -m 0750 /etc/pdi
sudo install -o pdi -g pdi -m 0600 \
  /opt/pdi/deployment/pdi.env.example /etc/pdi/pdi.env
sudoedit /etc/pdi/pdi.env
```

Set `DATABASE__URL` and one complete Provider group. For Nextcloud that means
`NEXTCLOUD__URL`, `NEXTCLOUD__USER`, and `NEXTCLOUD__PASSWORD`. Prefer a
dedicated read-only-capable account or app password according to the Provider's
own access model. Do not configure Immich or Gmail merely to satisfy PDI.

## 4. Apply database migrations

The existing Alembic tree is authoritative:

```bash
sudo -u pdi sh -c '
  set -a
  . /etc/pdi/pdi.env
  set +a
  cd /opt/pdi
  exec .venv/bin/alembic -c alembic.ini upgrade head
'
```

This reads the protected configuration inside the process; it does not place
the database password in command arguments.

Migrations are intentionally a source-install capability in this release. The
built wheel exposes the runtime CLI but does not include the repository-level
Alembic tree.

## 5. Run one Provider sync

```bash
sudo -u pdi sh -c '
  set -a
  . /etc/pdi/pdi.env
  set +a
  cd /opt/pdi
  exec .venv/bin/pdi sync --provider nextcloud
'
```

For an Immich-only deployment, configure only the Immich group and replace
`nextcloud` with `immich`. Running `pdi sync` without `--provider` includes
configured Nextcloud and Immich Providers, but never Gmail. It fails clearly
when neither eligible Provider is configured.

## 6. Connect an MCP consumer

`pdi mcp` runs the read-only MCP server over stdio; it opens no network
listener. A generic local MCP client can launch the protected wrapper:

```json
{
  "mcpServers": {
    "pdi": {
      "command": "/opt/pdi/deployment/mcp/pdi-mcp",
      "args": []
    }
  }
}
```

Run the consumer under an account authorized to execute the wrapper and read
the protected PDI configuration. If the client has its own reviewed secret
injection mechanism, it may instead launch `/opt/pdi/.venv/bin/pdi` with
`["mcp"]` and supply `DATABASE__URL` there. Immich configuration is optional
for MCP; when present it enables Immich semantic retrieval.

The consumer should query the public MCP tools and retain opaque
`pdi:resource:<uuid>` references. It must not access the PDI database, ORM, or
Provider credentials directly.

## 7. Optional scheduled operation

The files in [`deployment/systemd`](../../deployment/systemd/) are generic
reference units for `/opt/pdi`, the `pdi` account, and
`/etc/pdi/pdi.env`. Install only the Provider services and timers you intend to
operate, review their schedules first, then use normal systemd installation and
enablement procedures.

The scheduled services use `pdi.operational` to retain the formal global lock
and PipelineRun ledger. Gmail has no timer. The units are reference assets, not
an installer, and installing them is optional for manual use.

## Network and security boundary

PDI MCP uses stdio. PostgreSQL defaults to loopback in the Compose reference.
The optional Resource Access service uses an AF_UNIX socket. PDI does not
require Tailscale, a reverse proxy, or public Internet exposure; choose and
review any remote access topology separately. Read [SECURITY.md](../../SECURITY.md)
before introducing real credentials or personal-data fixtures.
