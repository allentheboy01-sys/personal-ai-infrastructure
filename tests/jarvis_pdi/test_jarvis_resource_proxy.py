import asyncio

import httpx
import pytest

from jarvis.pdi_client.resource_access import RepresentationError, ResourceAccessClient

REF = "pdi:resource:11111111-1111-4111-8111-111111111111"


def test_bounded_image_stream_and_validation():
    async def run():
        async def handler(request):
            return httpx.Response(200, headers={"content-type": "image/jpeg", "content-length": "4"}, content=b"data")
        client = ResourceAccessClient(None, transport=httpx.MockTransport(handler))
        async with client.stream(REF, "thumbnail") as stream:
            assert stream.content_type == "image/jpeg"
            assert b"".join([chunk async for chunk in stream.body]) == b"data"
        with pytest.raises(RepresentationError, match="invalid_resource_ref"):
            async with client.stream("bad", "thumbnail"): pass
        with pytest.raises(RepresentationError, match="unsupported_representation"):
            async with client.stream(REF, "original"): pass
    asyncio.run(run())

def test_oversized_and_unavailable_are_sanitized():
    async def run():
        async def oversized(request):
            return httpx.Response(200, headers={"content-type": "image/jpeg", "content-length": str(3 * 1024 * 1024)})
        with pytest.raises(RepresentationError, match="representation_too_large"):
            async with ResourceAccessClient(None, transport=httpx.MockTransport(oversized)).stream(REF, "thumbnail"): pass
        with pytest.raises(RepresentationError, match="representation_unavailable"):
            async with ResourceAccessClient(None).stream(REF, "thumbnail"): pass
    asyncio.run(run())


def test_video_stream_forwards_range_and_preserves_partial_response():
    async def run():
        seen_range = None

        class Chunks(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b"a"
                yield b"b"

        async def handler(request):
            nonlocal seen_range
            seen_range = request.headers.get("range")
            return httpx.Response(
                206,
                headers={
                    "content-type": "video/mp4",
                    "content-length": "2",
                    "content-range": "bytes 0-1/42",
                    "accept-ranges": "bytes",
                },
                stream=Chunks(),
            )

        client = ResourceAccessClient(
            None,
            transport=httpx.MockTransport(handler),
        )
        async with client.stream_video(REF, "bytes=0-1") as stream:
            assert stream.status_code == 206
            assert stream.content_type == "video/mp4"
            assert stream.content_length == 2
            assert stream.content_range == "bytes 0-1/42"
            assert stream.accept_ranges == "bytes"
            assert b"".join([chunk async for chunk in stream.body]) == b"ab"
        assert seen_range == "bytes=0-1"

    asyncio.run(run())


def test_video_unsatisfiable_range_is_sanitized_and_not_buffered():
    async def run():
        async def handler(request):
            return httpx.Response(
                416,
                headers={
                    "content-type": "application/json",
                    "content-length": "99",
                    "content-range": "bytes */42",
                    "accept-ranges": "bytes",
                },
                content=b'{"private":"provider response"}',
            )

        client = ResourceAccessClient(
            None,
            transport=httpx.MockTransport(handler),
        )
        async with client.stream_video(REF, "bytes=99-100") as stream:
            assert stream.status_code == 416
            assert stream.content_type is None
            assert stream.content_range == "bytes */42"
            assert b"".join([chunk async for chunk in stream.body]) == b""
        with pytest.raises(RepresentationError, match="unsupported_range"):
            async with client.stream_video(REF, "bytes=0-1,4-5"):
                pass

    asyncio.run(run())
