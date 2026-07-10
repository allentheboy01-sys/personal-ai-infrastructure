import os

from adapters.nextcloud.adapter import NextcloudAdapter
from engine import SyncEngine
from identity import Matcher
from repository import InMemoryRepository


def main() -> None:
    adapter = NextcloudAdapter(
        base_url=os.environ["NEXTCLOUD_URL"],
        username=os.environ["NEXTCLOUD_USER"],
        password=os.environ["NEXTCLOUD_PASSWORD"],
    )

    repository = InMemoryRepository()
    matcher = Matcher()

    engine = SyncEngine(
        adapter=adapter,
        matcher=matcher,
        repository=repository,
    )

    engine.sync_once()

    print("Sync finished.")
    print(f"Assets: {len(repository.assets)}")
    print(f"Blobs: {len(repository.blobs)}")
    print(f"Sources: {len(repository.sources)}")

    for asset in repository.assets.values():
        print(f"Asset: {asset}")

    for blob in repository.blobs.values():
        print(f"Blob: {blob}")

    for source in repository.sources.values():
        print(f"Source: {source}")


if __name__ == "__main__":
    main()