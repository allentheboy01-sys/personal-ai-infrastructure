# Database Migrations

PDI uses Alembic as its authoritative database migration history.
SQLAlchemy ORM metadata declares the current application model.

`src/pdi/database/schema.sql` remains temporarily as a legacy V0.1
bootstrap reference. New databases must not use it as an independent
initialization path.

Run all commands from the repository root.

## Configuration

Migration commands read only:

```text
DATABASE__URL
```

They do not require Nextcloud settings. The URL may be supplied through
the environment or the ignored local `.env` file. Never place a real URL
or password in `alembic.ini`.

If `DATABASE__URL` is missing, database commands fail before opening a
connection. Commands that only inspect migration scripts, such as
`history` and `heads`, do not need a database URL.

## New Database

Create an empty PostgreSQL database, then run:

```bash
PYTHONPATH=src \
DATABASE__URL='postgresql+psycopg://user:password@host/pdi' \
python -m alembic -c alembic.ini upgrade head
```

Do not run `schema.sql` first and do not stamp an empty database. The
baseline migration creates the complete V0.1 schema and records its
revision.

Verify the revision:

```bash
PYTHONPATH=src \
DATABASE__URL='postgresql+psycopg://user:password@host/pdi' \
python -m alembic -c alembic.ini current --verbose
```

## Adopt an Existing V0.1 Database

An existing V0.1 database already contains `assets`, `blobs`, and
`asset_sources`. Running the baseline upgrade against it would attempt
to create those tables again and must not be done.

Before adoption:

1. Back up the database.
2. Confirm the hostname, port, database name, and PostgreSQL user.
3. Run the read-only schema preflight.
4. Review every reported difference.
5. Stamp the explicit baseline revision only when preflight reports no
   difference.
6. Verify the current revision and business data.

Run preflight:

```bash
PYTHONPATH=src \
DATABASE__URL='postgresql+psycopg://user:password@host/pdi' \
python -m pdi.database.schema_preflight
```

The preflight validates the effective `public` schema, tables, columns,
types, nullability, server defaults, primary keys, foreign keys,
`ON DELETE` behavior, unique constraints, `ix_blobs_hash`, and the
absence of an existing `alembic_version` table. It is read-only: it
does not stamp, upgrade, or repair the database.

After a successful preflight and human review:

```bash
PYTHONPATH=src \
DATABASE__URL='postgresql+psycopg://user:password@host/pdi' \
python -m alembic -c alembic.ini stamp 7452797c95ca
```

Do not use `stamp head` as a substitute for naming and reviewing the
approved baseline.

Verify:

```bash
PYTHONPATH=src \
DATABASE__URL='postgresql+psycopg://user:password@host/pdi' \
python -m alembic -c alembic.ini current --verbose
```

Stamping records migration identity but does not prove schema
correctness. Preflight is therefore mandatory.

## Routine Commands

Show migration history:

```bash
PYTHONPATH=src \
python -m alembic -c alembic.ini history --verbose
```

Show heads:

```bash
PYTHONPATH=src \
python -m alembic -c alembic.ini heads --verbose
```

Create an autogenerate candidate against a safe development database:

```bash
PYTHONPATH=src \
DATABASE__URL='postgresql+psycopg://user:password@host/pdi_development' \
python -m alembic -c alembic.ini revision \
  --autogenerate -m "describe approved schema change"
```

Autogenerate output is only a candidate. Review every operation,
especially `drop_table`, `drop_column`, constraint changes, type
changes, and server-default changes. Never execute an unreviewed
revision.

Upgrade:

```bash
PYTHONPATH=src \
DATABASE__URL='postgresql+psycopg://user:password@host/pdi' \
python -m alembic -c alembic.ini upgrade head
```

Downgrade one revision:

```bash
PYTHONPATH=src \
DATABASE__URL='postgresql+psycopg://user:password@host/pdi_test' \
python -m alembic -c alembic.ini downgrade -1
```

The baseline downgrade deletes all three V0.1 business tables. It must
only run against an explicitly isolated disposable test database. Never
downgrade the baseline on an adopted V0.1 database or a database
containing user data.

## Integration Test Safety

PostgreSQL integration tests use only:

```text
PDI_TEST_DATABASE_URL
```

The test database name must end with `_test`. If `DATABASE__URL` is also
set, the two URLs must differ. Tests never fall back to
`DATABASE__URL`; unsafe or missing configuration causes an explicit
skip.

Repository integration tests:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
PDI_TEST_DATABASE_URL='postgresql+psycopg://user:password@host/pdi_repository_test' \
python -m pytest -p no:cacheprovider \
tests/integration/repository/test_repository.py
```

Migration integration tests:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
PDI_TEST_DATABASE_URL='postgresql+psycopg://user:password@host/pdi_migration_test' \
python -m pytest -p no:cacheprovider \
tests/integration/database/test_migrations.py
```

Migration tests destructively recreate only the approved PDI tables in
that isolated test database. They cover:

- ORM metadata registration;
- empty-database upgrade;
- V0.1 schema reflection;
- upgrade, downgrade, and re-upgrade;
- legacy `schema.sql` preflight and explicit baseline stamp;
- preservation of sample UUIDs and data during stamp;
- zero-diff autogenerate, including JSONB server defaults.

## Source-of-Truth Rule

After Step 0.5:

```text
Alembic revisions = authoritative migration history
ORM metadata       = current model declaration
schema.sql          = legacy V0.1 reference
```

Do not independently edit `schema.sql` for future schema changes.
Every approved change must receive its own reviewed Alembic revision
and matching ORM update.
