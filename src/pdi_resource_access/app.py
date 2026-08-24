from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from pdi.resource_access import (
    AmbiguousAccessSourceError,
    InvalidResourceReferenceError,
    ProviderInvalidResponseError,
    ProviderUnavailableError,
    RepresentationTooLargeError,
    RepresentationUnavailableError,
    ResourceAccessError,
    ResourceAccessService,
    ResourceAccessUnavailableError,
    ResourceNotFoundError,
    UnsupportedRepresentationError,
)


_STATUS_BY_ERROR = {
    InvalidResourceReferenceError: 400,
    UnsupportedRepresentationError: 422,
    ResourceNotFoundError: 404,
    RepresentationUnavailableError: 404,
    AmbiguousAccessSourceError: 409,
    RepresentationTooLargeError: 413,
    ProviderInvalidResponseError: 502,
    ProviderUnavailableError: 503,
    ResourceAccessUnavailableError: 503,
}


def _error_response(error: ResourceAccessError) -> JSONResponse:
    status = 500
    for error_type, mapped_status in _STATUS_BY_ERROR.items():
        if isinstance(error, error_type):
            status = mapped_status
            break
    return JSONResponse(
        {
            "error": {
                "code": error.code,
                "message": str(error),
            }
        },
        status_code=status,
        headers={"Cache-Control": "no-store"},
    )


def create_app(
    service: ResourceAccessService,
    *,
    shutdown: Callable[[], Awaitable[None]] | None = None,
) -> Starlette:
    @asynccontextmanager
    async def lifespan(app: Starlette):
        del app
        try:
            yield
        finally:
            if shutdown is not None:
                await shutdown()

    async def representation(request: Request) -> Response:
        try:
            opened = await service.open_representation(
                request.path_params["resource_ref"],
                request.path_params["representation_kind"],
            )
        except ResourceAccessError as error:
            return _error_response(error)

        descriptor = opened.descriptor
        headers = {"Cache-Control": "private, max-age=0"}
        if descriptor.content_length is not None:
            headers["Content-Length"] = str(descriptor.content_length)
        if descriptor.etag is not None:
            headers["ETag"] = descriptor.etag
        if descriptor.last_modified is not None:
            headers["Last-Modified"] = descriptor.last_modified

        async def body() -> AsyncIterator[bytes]:
            try:
                async for chunk in opened:
                    yield chunk
            finally:
                await opened.aclose()

        return StreamingResponse(
            body(),
            media_type=descriptor.media_type,
            headers=headers,
            background=BackgroundTask(opened.aclose),
        )

    async def video(request: Request) -> Response:
        try:
            opened = await service.open_video(
                request.path_params["resource_ref"],
                request.headers.get("range"),
            )
        except ResourceAccessError as error:
            return _error_response(error)

        descriptor = opened.descriptor
        headers = {"Cache-Control": "private, no-store"}
        if descriptor.content_length is not None:
            headers["Content-Length"] = str(descriptor.content_length)
        if descriptor.content_range is not None:
            headers["Content-Range"] = descriptor.content_range
        if descriptor.accept_ranges is not None:
            headers["Accept-Ranges"] = descriptor.accept_ranges

        async def body() -> AsyncIterator[bytes]:
            try:
                async for chunk in opened:
                    yield chunk
            finally:
                await opened.aclose()

        return StreamingResponse(
            body(),
            status_code=descriptor.status_code,
            media_type=descriptor.media_type,
            headers=headers,
            background=BackgroundTask(opened.aclose),
        )

    return Starlette(
        routes=[
            Route(
                "/v1/resources/{resource_ref}/representations/"
                "{representation_kind}",
                representation,
                methods=["GET"],
            ),
            Route(
                "/v1/resources/{resource_ref}/video",
                video,
                methods=["GET"],
            ),
        ],
        lifespan=lifespan,
    )
