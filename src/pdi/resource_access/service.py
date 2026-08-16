import asyncio
from collections.abc import AsyncIterator, Mapping
import re

import anyio

from pdi.query.errors import InvalidResourceRefError
from pdi.query.resources import parse_resource_ref

from .errors import (
    AmbiguousAccessSourceError,
    InvalidResourceReferenceError,
    ProviderInvalidResponseError,
    ProviderUnavailableError,
    RepresentationTooLargeError,
    RepresentationUnavailableError,
    ResourceAccessError,
    ResourceAccessUnavailableError,
    ResourceNotFoundError,
    UnsupportedRepresentationError,
)
from .models import (
    ResourceAccessSource,
    ResourceRepresentation,
    ResourceRepresentationDescriptor,
    ResourceRepresentationKind,
)
from .provider import (
    ProviderRepresentation,
    ProviderRepresentationAdapter,
)
from .repository import ResourceAccessRepository


THUMBNAIL_MAX_BYTES = 2 * 1024 * 1024
PREVIEW_MAX_BYTES = 16 * 1024 * 1024
MAX_ACTIVE_STREAMS = 8
_IMAGE_MEDIA_TYPE = re.compile(
    r"image/[a-z0-9!#$&^_.+\-]+",
)


class ResourceAccessService:
    def __init__(
        self,
        repository: ResourceAccessRepository,
        provider_adapters: Mapping[str, ProviderRepresentationAdapter],
        *,
        max_active_streams: int = MAX_ACTIVE_STREAMS,
    ) -> None:
        if max_active_streams < 1:
            raise ValueError("max_active_streams must be positive")
        self._repository = repository
        self._provider_adapters = dict(provider_adapters)
        self._semaphore = asyncio.Semaphore(max_active_streams)

    async def open_representation(
        self,
        resource_ref: str,
        representation_kind: ResourceRepresentationKind | str,
    ) -> ResourceRepresentation:
        try:
            asset_id = parse_resource_ref(resource_ref)
        except InvalidResourceRefError as error:
            raise InvalidResourceReferenceError(
                "Resource reference is invalid"
            ) from error

        try:
            kind = ResourceRepresentationKind(representation_kind)
        except (TypeError, ValueError) as error:
            raise UnsupportedRepresentationError(
                "Representation kind is unsupported"
            ) from error

        try:
            sources = await anyio.to_thread.run_sync(
                self._repository.resolve_access_sources,
                asset_id,
            )
        except Exception:
            raise ResourceAccessUnavailableError(
                "Resource access persistence is unavailable"
            ) from None
        if sources is None:
            raise ResourceNotFoundError("Resource was not found")

        eligible = tuple(
            source
            for source in sources
            if self._is_eligible(source)
        )
        if not eligible:
            raise RepresentationUnavailableError(
                "Representation is unavailable"
            )
        if len(eligible) > 1:
            raise AmbiguousAccessSourceError(
                "Resource has multiple eligible access Sources"
            )

        source = eligible[0]
        adapter = self._provider_adapters[source.provider]
        await self._semaphore.acquire()
        released = False
        upstream: ProviderRepresentation | None = None

        async def finish() -> None:
            nonlocal released
            if released:
                return
            released = True
            try:
                if upstream is not None:
                    await upstream.close()
            finally:
                self._semaphore.release()

        try:
            upstream = await adapter.open_representation(
                source.provider_locator,
                kind,
            )
            descriptor, declared_length = self._validate_upstream(
                resource_ref=resource_ref,
                kind=kind,
                source=source,
                upstream=upstream,
            )
        except BaseException:
            await finish()
            raise

        max_bytes = self._max_bytes(kind)

        async def bounded_body() -> AsyncIterator[bytes]:
            actual_length = 0
            try:
                async for chunk in upstream.body:
                    if not isinstance(chunk, (bytes, bytearray, memoryview)):
                        raise ProviderInvalidResponseError(
                            "Provider returned an invalid byte stream"
                        )
                    normalized = bytes(chunk)
                    if not normalized:
                        continue
                    actual_length += len(normalized)
                    if actual_length > max_bytes:
                        raise RepresentationTooLargeError(
                            "Representation exceeded its byte limit"
                        )
                    yield normalized
                if actual_length == 0:
                    raise ProviderInvalidResponseError(
                        "Provider returned an empty representation"
                    )
                if (
                    declared_length is not None
                    and actual_length != declared_length
                ):
                    raise ProviderInvalidResponseError(
                        "Provider Content-Length did not match the stream"
                    )
            except asyncio.CancelledError:
                raise
            except (ProviderUnavailableError, ResourceAccessError):
                raise
            except Exception as error:
                raise ProviderUnavailableError(
                    "Provider representation stream failed"
                ) from None
            finally:
                await finish()

        return ResourceRepresentation(
            descriptor=descriptor,
            body=bounded_body(),
            close=finish,
        )

    def _is_eligible(self, source: ResourceAccessSource) -> bool:
        return (
            source.provider == "immich"
            and source.provider in self._provider_adapters
            and source.resource_type == "file"
            and source.mime_type.lower().startswith("image/")
        )

    @staticmethod
    def _max_bytes(kind: ResourceRepresentationKind) -> int:
        if kind is ResourceRepresentationKind.THUMBNAIL:
            return THUMBNAIL_MAX_BYTES
        return PREVIEW_MAX_BYTES

    @classmethod
    def _validate_upstream(
        cls,
        *,
        resource_ref: str,
        kind: ResourceRepresentationKind,
        source: ResourceAccessSource,
        upstream: ProviderRepresentation,
    ) -> tuple[ResourceRepresentationDescriptor, int | None]:
        if upstream.status_code >= 500:
            raise ProviderUnavailableError(
                "Provider representation service is unavailable"
            )
        if upstream.status_code != 200:
            raise ProviderInvalidResponseError(
                "Provider returned an unexpected status"
            )

        raw_media_type = upstream.media_type
        if not isinstance(raw_media_type, str):
            raise ProviderInvalidResponseError(
                "Provider returned no valid Content-Type"
            )
        media_type = raw_media_type.split(";", 1)[0].strip().lower()
        if _IMAGE_MEDIA_TYPE.fullmatch(media_type) is None:
            raise ProviderInvalidResponseError(
                "Provider returned no valid Content-Type"
            )

        declared_length: int | None = None
        if upstream.content_length is not None:
            try:
                declared_length = int(upstream.content_length)
            except (TypeError, ValueError) as error:
                raise ProviderInvalidResponseError(
                    "Provider returned an invalid Content-Length"
                ) from error
            if declared_length <= 0:
                raise ProviderInvalidResponseError(
                    "Provider returned an invalid Content-Length"
                )
            if declared_length > cls._max_bytes(kind):
                raise RepresentationTooLargeError(
                    "Representation exceeded its byte limit"
                )

        return (
            ResourceRepresentationDescriptor(
                resource_ref=resource_ref,
                representation_kind=kind,
                media_type=media_type,
                content_length=declared_length,
                etag=upstream.etag,
                last_modified=upstream.last_modified,
                provider=source.provider,
            ),
            declared_length,
        )
