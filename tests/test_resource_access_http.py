import asyncio
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
from uuid import uuid4

import httpx

from pdi.query import format_resource_ref, parse_resource_ref
from pdi.resource_access import (
    ProviderRepresentation,
    ResourceAccessService,
    ResourceAccessSource,
)
from pdi_resource_access import create_app, create_uds_server, serve_uds


def _source(locator: str, mime_type: str = "image/jpeg") -> ResourceAccessSource:
    return ResourceAccessSource(
        provider="immich",
        provider_locator=locator,
        resource_type="file",
        mime_type=mime_type,
    )


class RouteRepository:
    def __init__(self, mappings) -> None:
        self.mappings = mappings

    def resolve_access_sources(self, asset_id: str):
        if asset_id == "00000000-0000-4000-8000-000000000001":
            raise RuntimeError(
                "password=private postgresql://role:private@database/pdi"
            )
        return self.mappings.get(asset_id)


class RouteAdapter:
    provider = "immich"

    async def open_representation(self, locator, kind):
        del kind
        behavior = {
            "thumbnail": (200, "image/webp", b"thumb"),
            "preview": (200, "image/jpeg", b"preview"),
            "oversized": (200, "image/webp", b""),
            "invalid": (302, "text/html", b""),
            "unavailable": (503, "application/json", b""),
        }[locator]
        status, media_type, payload = behavior

        async def body():
            yield payload

        async def close():
            return None

        content_length = (
            str(2 * 1024 * 1024 + 1)
            if locator == "oversized"
            else str(len(payload))
        )
        return ProviderRepresentation(
            status_code=status,
            media_type=media_type,
            content_length=content_length,
            etag='"safe-etag"',
            last_modified="Sat, 16 Aug 2026 00:00:00 GMT",
            body=body(),
            close=close,
        )

    async def open_video(self, locator, byte_range):
        assert byte_range == "bytes=0-0"

        async def body():
            if locator == "video":
                yield b"v"

        async def close():
            return None

        if locator == "video-unsat":
            return ProviderRepresentation(
                416,
                "application/json",
                "30",
                None,
                None,
                body(),
                close,
                content_range="bytes */42",
                accept_ranges="bytes",
            )
        return ProviderRepresentation(
            206,
            "video/mp4",
            "1",
            None,
            None,
            body(),
            close,
            content_range="bytes 0-0/42",
            accept_ranges="bytes",
        )

    async def aclose(self):
        return None


def test_real_uds_http_contract_and_socket_lifecycle() -> None:
    ids = {name: str(uuid4()) for name in (
        "thumbnail",
        "preview",
        "unavailable-resource",
        "ambiguous",
        "oversized",
        "invalid",
        "unavailable",
        "video",
        "video-unsat",
    )}
    mappings = {
        ids["thumbnail"]: (_source("thumbnail"),),
        ids["preview"]: (_source("preview"),),
        ids["unavailable-resource"]: (),
        ids["ambiguous"]: (_source("thumbnail"), _source("preview")),
        ids["oversized"]: (_source("oversized"),),
        ids["invalid"]: (_source("invalid"),),
        ids["unavailable"]: (_source("unavailable"),),
        ids["video"]: (_source("video", "video/mp4"),),
        ids["video-unsat"]: (
            _source("video-unsat", "video/quicktime"),
        ),
    }
    adapter = RouteAdapter()
    service = ResourceAccessService(
        RouteRepository(mappings),
        {adapter.provider: adapter},
    )
    app = create_app(service)
    async def run(socket_path: Path) -> None:
        server = create_uds_server(app)
        task = asyncio.create_task(
            serve_uds(app, socket_path, server=server)
        )
        for _ in range(200):
            if server.started:
                break
            if task.done():
                await task
            await asyncio.sleep(0.01)
        assert server.started
        assert socket_path.exists()
        assert stat.S_IMODE(socket_path.stat().st_mode) == 0o600
        assert stat.S_IMODE(socket_path.parent.stat().st_mode) == 0o700

        transport = httpx.AsyncHTTPTransport(uds=str(socket_path))
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://resource-access",
        ) as client:
            async def get(name: str, kind: str = "thumbnail"):
                ref = format_resource_ref(ids[name])
                return await client.get(
                    f"/v1/resources/{ref}/representations/{kind}"
                )

            thumbnail = await get("thumbnail")
            assert thumbnail.status_code == 200
            assert thumbnail.content == b"thumb"
            assert thumbnail.headers["content-type"] == "image/webp"
            assert thumbnail.headers["content-length"] == "5"
            assert thumbnail.headers["etag"] == '"safe-etag"'
            assert thumbnail.headers["cache-control"].startswith("private")

            preview = await get("preview", "preview")
            assert preview.status_code == 200
            assert preview.content == b"preview"
            assert preview.headers["content-type"] == "image/jpeg"

            video_ref = format_resource_ref(ids["video"])
            video = await client.get(
                f"/v1/resources/{video_ref}/video",
                headers={"Range": "bytes=0-0"},
            )
            assert video.status_code == 206
            assert video.content == b"v"
            assert video.headers["content-type"] == "video/mp4"
            assert video.headers["content-range"] == "bytes 0-0/42"
            assert video.headers["accept-ranges"] == "bytes"
            assert video.headers["content-length"] == "1"

            unsat_ref = format_resource_ref(ids["video-unsat"])
            unsat = await client.get(
                f"/v1/resources/{unsat_ref}/video",
                headers={"Range": "bytes=0-0"},
            )
            assert unsat.status_code == 416
            assert unsat.content == b""
            assert unsat.headers["content-range"] == "bytes */42"
            assert "private" not in unsat.text

            invalid_ref = await client.get(
                "/v1/resources/pdi:resource:not-a-uuid/"
                "representations/thumbnail"
            )
            missing = await client.get(
                f"/v1/resources/{format_resource_ref(uuid4())}/"
                "representations/thumbnail"
            )
            unsupported = await get("thumbnail", "original")
            no_source = await get("unavailable-resource")
            ambiguous = await get("ambiguous")
            oversized = await get("oversized")
            invalid = await get("invalid")
            unavailable = await get("unavailable")
            persistence_failure = await client.get(
                "/v1/resources/"
                "pdi:resource:00000000-0000-4000-8000-000000000001/"
                "representations/thumbnail"
            )

            expected = (
                (invalid_ref, 400, "invalid_resource_ref"),
                (missing, 404, "resource_not_found"),
                (unsupported, 422, "unsupported_representation"),
                (no_source, 404, "representation_unavailable"),
                (ambiguous, 409, "ambiguous_access_source"),
                (oversized, 413, "representation_too_large"),
                (invalid, 502, "provider_invalid_response"),
                (unavailable, 503, "provider_unavailable"),
                (
                    persistence_failure,
                    503,
                    "resource_access_unavailable",
                ),
            )
            for response, status_code, code in expected:
                assert response.status_code == status_code
                assert response.json()["error"]["code"] == code
                serialized = response.text
                assert "x-api-key" not in serialized
                assert "private-provider" not in serialized

        server.should_exit = True
        await asyncio.wait_for(task, timeout=5)

    with TemporaryDirectory(prefix="pdi-ra-", dir="/tmp") as directory:
        socket_path = Path(directory) / "resource-access.sock"
        asyncio.run(run(socket_path))
        assert not socket_path.exists()
    assert all(parse_resource_ref(format_resource_ref(value)) == value for value in ids.values())


def test_uds_client_disconnect_closes_upstream_and_releases_slot() -> None:
    asset_id = str(uuid4())
    closed = asyncio.Event()

    class DisconnectAdapter:
        provider = "immich"

        def __init__(self) -> None:
            self.calls = 0

        async def open_representation(self, locator, kind):
            del locator, kind
            self.calls += 1
            call = self.calls

            async def body():
                if call == 1:
                    yield b"x" * (64 * 1024)
                    await asyncio.Event().wait()
                else:
                    yield b"ok"

            async def close():
                if call == 1:
                    closed.set()

            return ProviderRepresentation(
                200,
                "image/webp",
                None if call == 1 else "2",
                None,
                None,
                body(),
                close,
            )

        async def aclose(self):
            return None

    adapter = DisconnectAdapter()
    service = ResourceAccessService(
        RouteRepository({asset_id: (_source("slow"),)}),
        {adapter.provider: adapter},
        max_active_streams=1,
    )
    app = create_app(service)

    async def run(socket_path: Path) -> None:
        server = create_uds_server(app)
        task = asyncio.create_task(
            serve_uds(app, socket_path, server=server)
        )
        for _ in range(200):
            if server.started:
                break
            if task.done():
                await task
            await asyncio.sleep(0.01)
        assert server.started

        reader, writer = await asyncio.open_unix_connection(socket_path)
        resource_ref = format_resource_ref(asset_id)
        writer.write(
            (
                f"GET /v1/resources/{resource_ref}/representations/thumbnail "
                "HTTP/1.1\r\nHost: resource-access\r\n\r\n"
            ).encode("ascii")
        )
        await writer.drain()
        received = await reader.read(4096)
        assert b"HTTP/1.1 200 OK" in received
        writer.close()
        await writer.wait_closed()
        await asyncio.wait_for(closed.wait(), timeout=2)

        transport = httpx.AsyncHTTPTransport(uds=str(socket_path))
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://resource-access",
        ) as client:
            second = await asyncio.wait_for(
                client.get(
                    f"/v1/resources/{resource_ref}/representations/thumbnail"
                ),
                timeout=2,
            )
            assert second.status_code == 200
            assert second.content == b"ok"

        server.should_exit = True
        await asyncio.wait_for(task, timeout=5)

    with TemporaryDirectory(prefix="pdi-ra-", dir="/tmp") as directory:
        socket_path = Path(directory) / "resource-access.sock"
        asyncio.run(run(socket_path))
        assert not socket_path.exists()
