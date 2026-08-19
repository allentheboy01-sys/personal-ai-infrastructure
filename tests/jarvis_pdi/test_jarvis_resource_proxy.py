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
