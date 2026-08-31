from .errors import (
    AmbiguousAccessSourceError,
    AmbiguousTextContentError,
    ContentChangedSinceSyncError,
    InvalidResourceReferenceError,
    InvalidTextContentError,
    InvalidTextWindowError,
    ProviderInvalidResponseError,
    ProviderUnavailableError,
    RepresentationTooLargeError,
    RepresentationUnavailableError,
    ResourceAccessError,
    ResourceAccessUnavailableError,
    ResourceNotFoundError,
    TextTooLargeError,
    TextUnavailableError,
    UnsupportedRepresentationError,
)
from .immich import CHUNK_SIZE, ImmichRepresentationAdapter
from .models import (
    ResourceAccessSource,
    ResourceRepresentation,
    ResourceRepresentationDescriptor,
    ResourceRepresentationKind,
    ResourceVideo,
    ResourceVideoDescriptor,
)
from .provider import ProviderRepresentation, ProviderRepresentationAdapter
from .nextcloud_text import NextcloudTextAdapter, TEXT_CHUNK_SIZE
from .repository import ResourceAccessRepository, ResourceTextRepository
from .runtime import (
    ImmichResourceAccessRuntime,
    create_immich_resource_access_runtime,
)
from .service import (
    MAX_ACTIVE_STREAMS,
    PREVIEW_MAX_BYTES,
    THUMBNAIL_MAX_BYTES,
    ResourceAccessService,
)
from .text_models import (
    RESOURCE_TEXT_SCHEMA,
    ResourceText,
    TextResourceAccessSource,
)
from .text_provider import ProviderTextAdapter, ProviderTextContent
from .text_service import (
    DEFAULT_TEXT_WINDOW_BYTES,
    MAX_ACTIVE_TEXT_READS,
    MAX_TEXT_SOURCE_BYTES,
    MAX_TEXT_WINDOW_BYTES,
    MIN_TEXT_WINDOW_BYTES,
    ResourceTextService,
)

__all__ = [
    "AmbiguousAccessSourceError",
    "AmbiguousTextContentError",
    "CHUNK_SIZE",
    "ContentChangedSinceSyncError",
    "DEFAULT_TEXT_WINDOW_BYTES",
    "ImmichRepresentationAdapter",
    "ImmichResourceAccessRuntime",
    "InvalidResourceReferenceError",
    "InvalidTextContentError",
    "InvalidTextWindowError",
    "MAX_ACTIVE_STREAMS",
    "MAX_ACTIVE_TEXT_READS",
    "MAX_TEXT_SOURCE_BYTES",
    "MAX_TEXT_WINDOW_BYTES",
    "MIN_TEXT_WINDOW_BYTES",
    "NextcloudTextAdapter",
    "PREVIEW_MAX_BYTES",
    "ProviderInvalidResponseError",
    "ProviderRepresentation",
    "ProviderRepresentationAdapter",
    "ProviderTextAdapter",
    "ProviderTextContent",
    "ProviderUnavailableError",
    "RepresentationTooLargeError",
    "RepresentationUnavailableError",
    "ResourceAccessError",
    "ResourceAccessRepository",
    "ResourceAccessService",
    "ResourceAccessSource",
    "ResourceAccessUnavailableError",
    "ResourceNotFoundError",
    "ResourceText",
    "ResourceTextRepository",
    "ResourceTextService",
    "ResourceRepresentation",
    "ResourceRepresentationDescriptor",
    "ResourceRepresentationKind",
    "ResourceVideo",
    "ResourceVideoDescriptor",
    "THUMBNAIL_MAX_BYTES",
    "TEXT_CHUNK_SIZE",
    "TextResourceAccessSource",
    "TextTooLargeError",
    "TextUnavailableError",
    "UnsupportedRepresentationError",
    "create_immich_resource_access_runtime",
    "RESOURCE_TEXT_SCHEMA",
]
