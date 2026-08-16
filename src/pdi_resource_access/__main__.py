import asyncio
import os

from .bootstrap import create_runtime_app
from .uds import serve_uds


DEFAULT_SOCKET_PATH = "/run/pdi/resource-access.sock"


def main() -> None:
    socket_path = os.environ.get(
        "PDI_RESOURCE_ACCESS_SOCKET",
        DEFAULT_SOCKET_PATH,
    )
    asyncio.run(
        serve_uds(
            create_runtime_app(),
            socket_path,
        )
    )


if __name__ == "__main__":
    main()
