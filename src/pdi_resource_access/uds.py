import asyncio
from pathlib import Path
import socket
import stat

from starlette.types import ASGIApp
import uvicorn


def create_uds_server(app: ASGIApp) -> uvicorn.Server:
    return uvicorn.Server(
        uvicorn.Config(
            app,
            lifespan="on",
            log_level="warning",
            access_log=False,
        )
    )


def _bind_socket(socket_path: Path) -> socket.socket:
    if socket_path.exists():
        mode = socket_path.lstat().st_mode
        if not stat.S_ISSOCK(mode):
            raise RuntimeError("UDS path exists and is not a socket")
        socket_path.unlink()

    bound = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        bound.bind(str(socket_path))
        socket_path.chmod(0o600)
        bound.listen(socket.SOMAXCONN)
        bound.setblocking(False)
    except BaseException:
        bound.close()
        if socket_path.exists() and stat.S_ISSOCK(
            socket_path.lstat().st_mode
        ):
            socket_path.unlink()
        raise
    return bound


async def serve_uds(
    app: ASGIApp,
    socket_path: str | Path,
    *,
    server: uvicorn.Server | None = None,
) -> None:
    path = Path(socket_path)
    if not path.parent.exists():
        path.parent.mkdir(parents=True, mode=0o700)
    bound = _bind_socket(path)
    active_server = server or create_uds_server(app)
    try:
        await active_server.serve(sockets=[bound])
    finally:
        bound.close()
        await asyncio.sleep(0)
        if path.exists() and stat.S_ISSOCK(path.lstat().st_mode):
            path.unlink()
