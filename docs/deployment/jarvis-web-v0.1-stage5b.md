# Jarvis Web UI V0.1 — Stage 5B deployment runbook

## Status and immutable boundary

Stage 5B.0 production candidate; **not deployed**. The candidate starts from
`4a89bcf0421d25a5f2cde7bb504d5d2adc837859`. Replace `DEPLOY_SHA` below only
with the human-approved Stage 5B.0 freeze commit. Never run these commands from
an unclean checkout or against a divergent production checkout.

Target topology is Tailscale Serve HTTPS to `http://127.0.0.1:8765`, one
Uvicorn worker, separate `jarvis` PostgreSQL database, persistent PDI MCP stdio
child, Resource Access UDS, and one isolated Hermes bridge process per Turn.
There is no Funnel, public listener, Node server, Redis, queue, WebSocket, or
automatic migration.

Every lettered section is a separate human approval gate. Stop between gates.
Commands that contain a credential are entered interactively or read from a
protected file; never paste a value into shell history or the deployment log.

## A. PostgreSQL HBA hardening

Precondition: current HBA and the formal authenticated PDI URL have been
reconfirmed; a maintenance window and human approval exist.

```bash
sudo install -m 0600 -o root -g root /srv/appdata/pdi/postgres/pg_hba.conf \
  /srv/appdata/pdi/postgres/pg_hba.conf.pre-jarvis
sudoedit /srv/appdata/pdi/postgres/pg_hba.conf
```

Change only the existing host loopback rules for `127.0.0.1/32` and `::1/128`
from `trust` to `scram-sha-256`; retain the local Unix-socket and replication
rules unless separately reviewed. Then:

```bash
sudo docker exec pdi-postgres psql -U pdi -d postgres -v ON_ERROR_STOP=1 \
  -c "SELECT pg_reload_conf();"
sudo docker exec pdi-postgres psql -U pdi -d postgres -At \
  -c "SELECT line_number,type,address,auth_method,error FROM pg_hba_file_rules ORDER BY line_number;"
PGPASSWORD= psql -w -h 127.0.0.1 -p 5433 -U pdi -d pdi -c "SELECT 1"
sudo -u harry /srv/projects/PDI/deployment/jarvis/pdi-mcp
```

Expected: reload is true; host-loopback rows are `scram-sha-256` with no
error; the passwordless host command fails; the protected PDI launcher reaches
its normal MCP stdio handshake (terminate after validation without a write).
STOP on syntax errors or failure of the authenticated PDI path. Recovery:
restore `pg_hba.conf.pre-jarvis`, reload, and revalidate PDI before continuing.
Until this gate passes, `jarvis_app` is not a meaningful isolation boundary.

## B. Immutable runtime and artifact install

Precondition: approved commit is on `origin/main`; development and production
worktrees are clean and equal; Stage 5B.0 validation is green.

Build on the development checkout, not production runtime:

```bash
export DEPLOY_SHA=<approved-40-character-sha>
test "$(git rev-parse HEAD)" = "$DEPLOY_SHA"
test -z "$(git status --porcelain)"
python3.13 deployment/jarvis/web/build_release.py \
  --deploy-sha "$DEPLOY_SHA" --output-root /tmp/jarvis-web-release
python3.13 deployment/jarvis/web/verify_release.py \
  "/tmp/jarvis-web-release/$DEPLOY_SHA" --deploy-sha "$DEPLOY_SHA"
```

After human review, install without overwriting an existing release:

```bash
sudo install -d -m 0755 -o root -g root /opt/jarvis-web/releases
sudo install -d -m 0755 -o root -g root /opt/jarvis-web/venvs
sudo cp -a "/tmp/jarvis-web-release/$DEPLOY_SHA" "/opt/jarvis-web/releases/$DEPLOY_SHA"
sudo python3.13 -m venv "/opt/jarvis-web/venvs/$DEPLOY_SHA"
sudo "/opt/jarvis-web/venvs/$DEPLOY_SHA/bin/pip" install \
  --require-hashes -r "/opt/jarvis-web/releases/$DEPLOY_SHA/manifests/requirements-production.lock"
sudo "/opt/jarvis-web/venvs/$DEPLOY_SHA/bin/pip" install --no-deps \
  "/opt/jarvis-web/releases/$DEPLOY_SHA/app/"*.whl
sudo "/opt/jarvis-web/venvs/$DEPLOY_SHA/bin/pip" check
sudo python3.13 deployment/jarvis/web/verify_release.py \
  "/opt/jarvis-web/releases/$DEPLOY_SHA" --deploy-sha "$DEPLOY_SHA"
sudo chown -R root:root "/opt/jarvis-web/releases/$DEPLOY_SHA"
sudo chmod -R a-w "/opt/jarvis-web/releases/$DEPLOY_SHA"
sudo find "/opt/jarvis-web/releases/$DEPLOY_SHA" -type d ! -perm 0555 -print
sudo find "/opt/jarvis-web/releases/$DEPLOY_SHA" -type f ! -path '*/bin/hermes-bridge' ! -perm 0444 -print
sudo test "$(sudo stat -c %a "/opt/jarvis-web/releases/$DEPLOY_SHA/bin/hermes-bridge")" = 555
sudo -u harry test -r "/opt/jarvis-web/releases/$DEPLOY_SHA/static/index.html"
sudo -u harry test -x "/opt/jarvis-web/releases/$DEPLOY_SHA/bin/hermes-bridge"
```

Expected: one verified immutable release plus a SHA-specific dependency venv,
importable Jarvis-only wheel, green `pip check`, no
`node_modules`, browser runtime, review screenshot, or secret. STOP on a hash,
wheel, import, permission, or service-user access mismatch. The installed
release is `root:root`; directories are `0555`, ordinary files `0444`, and the
approved Hermes launcher is `0555`. Recovery: remove only the new incomplete release;
never overwrite the previous release. The frontend was built from
`package-lock.json`; Node is not installed or run by the service.

## C. Jarvis roles and database

Precondition: Gate A passed. In an interactive administrative `psql` session:

```bash
sudo docker exec -it pdi-postgres psql -U pdi -d postgres -v ON_ERROR_STOP=1
```

```sql
CREATE ROLE jarvis_owner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
\password jarvis_owner
CREATE ROLE jarvis_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
\password jarvis_app
CREATE DATABASE jarvis OWNER jarvis_owner;
REVOKE ALL ON DATABASE jarvis FROM PUBLIC;
GRANT CONNECT ON DATABASE jarvis TO jarvis_app;
```

Expected: both roles have no elevated attributes and only `jarvis_owner` owns
the separate database. Current UUID keys are generated client-side: the frozen
schema creates no PostgreSQL sequence, so no sequence grant is required. STOP
if any PDI grant appears or elevated attribute is required. Before migration,
recovery may drop only the newly created empty `jarvis` database/roles after
human confirmation. After migration, preserve the database.

## D. Protected configuration

Precondition: Gate C passed. Create two independent authorities:

- `/etc/jarvis/web.env`, `harry:harry`, `0600`: runtime DB URL, exact allowed
  Tailscale login, origin, immutable static path, launchers/socket, and bounds.
- `/etc/jarvis/migration.env`, `root:root`, `0600`: only the owner
  `JARVIS_DATABASE_URL` used by controlled Alembic deployment.

```bash
sudo install -d -m 0750 -o root -g harry /etc/jarvis
sudo install -m 0600 -o harry -g harry \
  deployment/jarvis/web/jarvis-web.env.example /etc/jarvis/web.env
sudo install -m 0600 -o root -g root /dev/null /etc/jarvis/migration.env
sudoedit /etc/jarvis/web.env
sudoedit /etc/jarvis/migration.env
```

Expected: no PDI/Provider/model credential in `web.env`; no runtime credential
in `migration.env`; values are never printed. STOP on broader modes or mixed
secret authority. Recovery: remove only new Jarvis config before service start.

## E. Migration and least-privilege grants

Precondition: Gates B–D passed; service is not running.

```bash
set -a; . /etc/jarvis/migration.env; set +a
cd "/opt/jarvis-web/releases/$DEPLOY_SHA/migrations"
sudo -E "/opt/jarvis-web/venvs/$DEPLOY_SHA/bin/alembic" \
  -c jarvis-alembic.ini upgrade head
unset JARVIS_DATABASE_URL
sudo docker exec -it pdi-postgres psql -U pdi -d jarvis -v ON_ERROR_STOP=1
```

```sql
GRANT USAGE ON SCHEMA public TO jarvis_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
  jarvis_conversations, jarvis_messages, jarvis_turns,
  jarvis_message_resource_refs TO jarvis_app;
ALTER DEFAULT PRIVILEGES FOR ROLE jarvis_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO jarvis_app;
SELECT version_num FROM jarvis_alembic_version;
SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;
SELECT sequencename FROM pg_sequences WHERE schemaname='public';
```

Expected: revision `1a2b3c4d5e6f`, exactly four domain tables plus
`jarvis_alembic_version`, and zero sequences. Future migrations must maintain
runtime grants explicitly; never give `jarvis_app` CREATE, ownership, or DDL.
STOP on PDI tables, sequences without reviewed grants, or schema drift. Do not
downgrade/delete a database with conversations as automatic recovery.

## F. systemd install and localhost start

Precondition: migrations and artifact verification passed. Install the stable
links atomically, then the reviewed unit:

```bash
sudo ln -sfn "/opt/jarvis-web/releases/$DEPLOY_SHA" /opt/jarvis-web/current.new
sudo mv -Tf /opt/jarvis-web/current.new /opt/jarvis-web/current
sudo ln -sfn "/opt/jarvis-web/venvs/$DEPLOY_SHA" /opt/jarvis-web/venv-current.new
sudo mv -Tf /opt/jarvis-web/venv-current.new /opt/jarvis-web/venv-current
sudo ln -sfn /opt/jarvis-web/current/bin/hermes-bridge \
  /usr/local/libexec/jarvis-web-hermes-bridge.new
sudo mv -Tf /usr/local/libexec/jarvis-web-hermes-bridge.new \
  /usr/local/libexec/jarvis-web-hermes-bridge
sudo install -m 0644 -o root -g root deployment/systemd/jarvis-web.service \
  /etc/systemd/system/jarvis-web.service
sudo systemd-analyze verify /etc/systemd/system/jarvis-web.service
sudo systemctl daemon-reload
sudo systemctl enable --now jarvis-web.service
curl --fail --silent --show-error http://127.0.0.1:8765/ -o /dev/null
sudo ss -ltnp | grep '127.0.0.1:8765'
```

Expected: one loopback listener, one worker, no default access log, no Node,
and no migration at startup. A direct localhost request to protected content
without Serve identity must be rejected. STOP on `0.0.0.0`, multiple workers,
child leaks, or protected-path access. Recovery: stop/disable unit, restore the
previous `current`, `venv-current`, and libexec symlinks, daemon-reload, and
start the prior release; preserve Jarvis DB.

Hermes 0.10.0 initializes `HERMES_HOME/sessions` and writes bounded agent logs
even when the Web bridge uses `persist_session=False`, `session_db=None`,
`save_trajectories=False`, and disabled checkpoints. The unit therefore keeps
`ProtectHome=read-only` and bind-mounts exactly two service-lifetime
`RuntimeDirectory` paths over the formal profile's `sessions/` and `logs/`
subdirectories. The formal profile configuration, Hermes venv, and the rest of
`~/.hermes` remain read-only. These transient files are non-authoritative and
are removed when the unit is stopped; Jarvis DB history remains the only
conversation authority. Do not replace this with `ProtectHome=no`, a writable
home, or a writable full profile.

Before a Gate E retry, validate the effective unit with
`systemd-analyze verify`, then use a transient unit with the same
`RuntimeDirectory`, `BindPaths`, `ProtectHome`, `PrivateTmp`, and inaccessible
paths. Require AIAgent initialization, one harmless general-tool Turn, removal
of both runtime directories after unit collection, zero bridge children, and a
second Turn driven only by normalized Jarvis history. STOP if Hermes requires
any additional writable profile path.

## G. Tailscale Serve and HTTPS

Precondition: localhost service and fail-closed auth are verified. Capture
current Serve state before the separately approved mutation:

```bash
sudo tailscale serve status --json > /tmp/jarvis-pre-serve.json
sudo tailscale funnel status --json
sudo tailscale serve --bg --https=443 http://127.0.0.1:8765
sudo tailscale serve status --json
sudo tailscale funnel status --json
```

Expected origin: `https://pdi-server.tailfdc57b.ts.net`. Expected backend:
exactly `http://127.0.0.1:8765`; Funnel remains off. STOP on public/Funnel
exposure, a different origin, or raw-port reachability. Recovery:
`sudo tailscale serve reset`, then restore only the captured prior routes after
human review.

## H. Real identity and security verification

Precondition: Gate G. Through Serve, exact allowlisted
`Tailscale-User-Login` succeeds. A missing, wrong, shared/tagged, or
client-spoofed identity fails. Direct loopback without injected identity fails.
Also test wrong/missing Origin, non-JSON mutation, missing
`X-Jarvis-Request: web-v1`, unknown/unauthorized Turn SSE, and confirm no trust
of `X-Forwarded-For`/`X-Real-IP`. Uvicorn remains `--no-proxy-headers`.
STOP and reset Serve if any negative case succeeds.

## I. Mac E2E

With the Mac on the tailnet: load HTTPS; create a conversation; run a bounded
Hermes Turn; observe existing phases and safe final response; refresh/reconnect;
cancel a Turn; open Resources, safe Resource Detail, eligible Immich preview,
and Providers. DevTools must reveal no Provider endpoint/credential, MCP, UDS,
or DB URL. Confirm port 8765 is unreachable remotely and Funnel has no public
path. Do not record private content. STOP on leakage or contract regression.

## J. iPhone Safari E2E

With Tailscale connected: validate HTTPS, drawer, keyboard/composer,
safe-area/100dvh, no horizontal overflow, stream/autoscroll, full-screen
Resource Detail, Providers, rotation, and bounded network interruption/reconnect.
No PWA/push is expected. STOP on an unusable mutation/cancel path.

## K. Backup continuity gate

Production smoke may use synthetic/disposable conversations before this gate,
but normal long-term use must not be declared ready until either:

1. existing encrypted off-host backup is proven to include the PostgreSQL
   storage and a restore of the separate `jarvis` database is validated; or
2. deployment stops for human approval of a minimal encrypted off-host
   `pg_dump`/restore procedure.

A dump on the same physical disk does not pass. Never delete the Jarvis
database because this gate is open. Recovery testing must use an isolated
database/server and must not overwrite production.

## L. Final freeze

Reverify artifact checksums; service/unit/config modes; one listener/worker;
Funnel off; exact identity and Origin; real bounded Hermes completion/cancel;
running Turn becomes `interrupted` after service restart; exact Turn process
group and MCP child cleanup; read-only Resources/Detail/Immich preview/
Providers/DataStatus; PDI writes 0 and Provider writes 0; database backup gate
closed. Record deployed SHA and aggregate results only. Then, and only then,
declare Stage 5 frozen.

## Production composition keys

| Classification | Keys |
|---|---|
| SECRET | `JARVIS_DATABASE_URL`, `JARVIS_ALLOWED_TAILSCALE_LOGIN` |
| DERIVED / DEPLOYMENT | `JARVIS_ALLOWED_ORIGIN`, `JARVIS_STATIC_DIR` |
| NON-SECRET | `JARVIS_HERMES_BRIDGE_COMMAND`, `JARVIS_PDI_MCP_COMMAND`, `JARVIS_RESOURCE_ACCESS_SOCKET`, `JARVIS_BIND_HOST`, `JARVIS_BIND_PORT`, `JARVIS_RUNTIME_*`, `JARVIS_PDI_*`, `JARVIS_RESOURCE_ACCESS_TIMEOUT_SECONDS` |

The Web process receives no PDI DB or Provider credential. The PDI launcher
loads its own protected authority. The separate Hermes launcher loads only the
model authority, then passes only `DEEPSEEK_API_KEY` through `env -i`.

## Capability and continuity notes

- PDI generic MCP tools: 8; Hermes PDI allowlist: 7; PDI pipelines: 10.
- Immich image representation is supported. Nextcloud preview and Gmail body
  remain unavailable. Agent-linked Resource refs remain deferred.
- Gmail existing PDI data is readable. Unattended Gmail sync is not ready and
  no timer is added by this deployment.
- Previous good application baseline is
  `4a89bcf0421d25a5f2cde7bb504d5d2adc837859`; application rollback preserves
  conversations and does not imply a database downgrade.
