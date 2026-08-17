# PDI Server Runtime V0.1

## Architecture

PDI automatic provider synchronization is a deployment-layer concern:

```text
systemd timer (when)
        ↓
systemd oneshot service
        ↓
global flock (mutual exclusion)
        ↓
pdi.main --provider (what)
        ↓
existing PDI Core
```

There is no Python scheduler. The services use the existing provider selection and
the existing ProviderFact → Matcher → Decision → SyncEngine → Repository pipeline.

## Runtime host

The formal runtime host is `pdi-server`. It must run independently of the Mac,
SSH tunnels, Mac paths, and Mac environment variables.

## Repository path

The canonical server checkout is `/srv/projects/PDI`. Deployment updates must be
fast-forward-only from the authoritative Git remote.

## Runtime user

Both services run as `harry`. V0.1 does not introduce a dedicated service user.
The services do not require access to the Docker socket.

## Python and virtual environment

The runtime interpreter is `/srv/projects/PDI/.venv/bin/python`. Reuse this
virtual environment; do not create a second production environment or install
project dependencies globally.

## Secret location

The runtime environment file is `/etc/pdi/pdi.env`, owned by `harry:harry` with
mode `600`. It contains the six settings named by
`deployment/pdi.env.example`. Never commit or log its values.

The repository-local `.env` is legacy state and is not the formal runtime
authority after service validation.

## Production endpoints

- PDI PostgreSQL: `127.0.0.1:5433`
- Nextcloud: `http://127.0.0.1:8080`
- Immich: `http://127.0.0.1:2283`

The PostgreSQL service on `127.0.0.1:55432` is isolated test infrastructure and
must never be used by the production services.

## Services

- `pdi-sync-nextcloud.service`
- `pdi-sync-immich.service`

Each is a system-level `Type=oneshot` unit with the repository as its working
directory and `/etc/pdi/pdi.env` as its explicit environment source.

## Timers and cadence

- `pdi-sync-nextcloud.timer`: daily at 02:15 server local time
- `pdi-sync-immich.timer`: daily at 05:15 server local time

Both timers use `Persistent=true`. The three-hour offset reduces normal lock
contention. The cadence is deployment configuration, not a PDI Core contract.

## Global lock

Both services take an exclusive lock on `/run/lock/pdi-sync.lock`. A contender
waits at most 3,600 seconds, then exits non-zero instead of running concurrently
or waiting forever. Each complete service run has a 12-hour upper bound so a
stuck provider cannot occupy the runtime indefinitely.

## Logging

Standard output and error go to journald. Provider credentials and complete
database URLs must not be written to logs.

Inspect recent logs with:

```bash
sudo journalctl -u pdi-sync-nextcloud.service -n 200 --no-pager
sudo journalctl -u pdi-sync-immich.service -n 200 --no-pager
```

## Manual service execution

Run through systemd so the same user, working directory, environment, lock, and
logging behavior are exercised as scheduled execution:

```bash
sudo systemctl start pdi-sync-nextcloud.service
sudo systemctl start pdi-sync-immich.service
```

Run Immich only after the Nextcloud smoke test passes.

## Status inspection

```bash
sudo systemctl status pdi-sync-nextcloud.service --no-pager
sudo systemctl status pdi-sync-immich.service --no-pager
```

For a successful oneshot unit, `inactive (dead)` after completion is normal; the
important result is `Result=success` and exit status zero.

## Timer inspection

```bash
systemctl list-timers 'pdi-sync-*' --all
systemctl show pdi-sync-nextcloud.timer -p UnitFileState -p Persistent -p NextElapseUSecRealtime
systemctl show pdi-sync-immich.timer -p UnitFileState -p Persistent -p NextElapseUSecRealtime
```

## Git update procedure

Before updating, confirm the checkout is clean and prevent overlap with provider
synchronization. Then use only a fast-forward update:

```bash
cd /srv/projects/PDI
git status --short --branch
git fetch origin
git pull --ff-only origin main
```

Stop if the worktree is dirty or a fast-forward is not possible. Do not reset,
rebase, force checkout, or create a merge commit on the runtime host.

## Dependency synchronization

After every repository update that can change dependencies:

```bash
cd /srv/projects/PDI
.venv/bin/python -m pip install -e .
.venv/bin/python -m pip check
.venv/bin/python -c "import pdi; print(pdi.__file__)"
```

Validate required optional entrypoints separately without displaying environment
variables or credentials.

## Unit installation

Install the canonical repository files; do not maintain divergent hand-written
copies:

```bash
sudo install -o root -g root -m 0644 deployment/systemd/pdi-sync-nextcloud.service /etc/systemd/system/
sudo install -o root -g root -m 0644 deployment/systemd/pdi-sync-nextcloud.timer /etc/systemd/system/
sudo install -o root -g root -m 0644 deployment/systemd/pdi-sync-immich.service /etc/systemd/system/
sudo install -o root -g root -m 0644 deployment/systemd/pdi-sync-immich.timer /etc/systemd/system/
sudo systemctl daemon-reload
```

Do not enable the timers until both services pass manual smoke validation.

## Smoke validation

Validate in this order:

1. Confirm the environment file exists, has owner `harry:harry`, and mode `600`.
2. Confirm `DATABASE__URL` resolves to the formal database on port `5433`.
3. Query `current_database()` and `current_user`; never print the password.
4. Confirm read-only Nextcloud and Immich connectivity through loopback endpoints.
5. Start the Nextcloud service and inspect its exit result and journal.
6. Confirm synchronized Resources remain readable through the existing query path.
7. Start Immich and stop review if hashes, actions, downloads, or deactivations are
   unexpectedly large.
8. Confirm existing Source and Blob identity remain stable for unchanged assets.
9. Validate that both services reference the same lock path.
10. Enable timers only after all preceding checks pass.

Do not run pytest against the production database.

## Enabling scheduling

After successful service validation:

```bash
sudo systemctl enable --now pdi-sync-nextcloud.timer
sudo systemctl enable --now pdi-sync-immich.timer
systemctl list-timers 'pdi-sync-*' --all
```

No reboot is required for V0.1 validation. Enabled state plus `Persistent=true`
provides configuration-level reboot persistence.

## Failure semantics

A provider exception, lock timeout, or 12-hour service timeout produces a failed
systemd invocation and journald evidence. V0.1 has no automatic retry queue,
backoff, or restart loop. The next normal timer occurrence is the next attempt.

Never compensate for a failure by editing the production database manually.

## Secret rotation

1. Disable or stop the affected timer.
2. Wait for the global sync lock to become available.
3. Replace `/etc/pdi/pdi.env` atomically while preserving owner `harry:harry` and
   mode `600`.
4. Run read-only connectivity checks without printing values.
5. Start the affected service manually and inspect its result.
6. Re-enable the timer after successful validation.

No service daemon caches the file: each oneshot invocation reads it again.

## Rollback considerations

- Keep the previous known-good Git commit identifier before updating.
- Stop timers before a code rollback.
- Roll back only with an explicit reviewed Git operation; never use
  `git reset --hard` as an operational shortcut.
- Re-synchronize the existing virtual environment after changing commits.
- Reinstall matching canonical unit files and run `daemon-reload` if deployment
  artifacts changed.
- Do not downgrade or alter the production schema unless a separately reviewed
  migration plan explicitly requires it.

## Development and production responsibilities

The workstation remains available for review and administration, but primary
development may run on `pdi-server` in the separate user-owned checkout
`/home/harry/projects/personal-ai-infrastructure`.

`/srv/projects/PDI` remains the formal production checkout. It owns the
production virtual environment, deployment artifacts, scheduling, Provider
connectivity, synchronization, and production PostgreSQL access. Never use it
as a Codex development worktree or pytest target. See
`docs/development/codex-cli-on-pdi-server.md` for the isolated host workflow.
