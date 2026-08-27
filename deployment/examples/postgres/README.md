# PostgreSQL 16 reference

PDI needs PostgreSQL for durable state, but it does not require Docker. Use
this reference only when you do not already operate PostgreSQL 16.

```bash
cd deployment/examples/postgres
cp .env.example .env
# Replace POSTGRES_PASSWORD in .env with a strong deployment-specific value.
docker compose up -d
```

The database publishes on `127.0.0.1:5432` by default and stores data in the
named volume `pdi-postgres-data`. Do not change the bind address to a public
interface without a separately reviewed network and authentication design.

Set PDI's `DATABASE__URL` to the matching SQLAlchemy URL. The committed
`.env.example` is synthetic; never commit the populated `.env` file.
