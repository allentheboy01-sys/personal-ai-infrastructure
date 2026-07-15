import os
from dotenv import load_dotenv

load_dotenv()
from adapters.nextcloud.adapter import NextcloudAdapter
from engine import SyncEngine
from identity import Matcher
from database import create_postgres_engine
from repository import PostgreSQLRepository

def main() -> None:
    adapter = NextcloudAdapter(
        base_url=os.environ["NEXTCLOUD_URL"],
        username=os.environ["NEXTCLOUD_USER"],
        password=os.environ["NEXTCLOUD_PASSWORD"],
    )

    db_engine = create_postgres_engine()

    repository = PostgreSQLRepository(
        db_engine,
    )

    matcher = Matcher()

    sync_engine = SyncEngine(
        adapter=adapter,
        matcher=matcher,
        repository=repository,
    )

    sync_engine.sync_once()

    print("Sync finished.")


if __name__ == "__main__":
    main()