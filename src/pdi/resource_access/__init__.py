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
from .repository import ResourceAccessRepository
from .service import (
    MAX_ACTIVE_STREAMS,
    PREVIEW_MAX_BYTES,
    THUMBNAIL_MAX_BYTES,
    ResourceAccessService,
)

__all__ = [
    "AmbiguousAccessSourceError",
    "CHUNK_SIZE",
    "ImmichRepresentationAdapter",
    "InvalidResourceReferenceError",
    "MAX_ACTIVE_STREAMS",
    "PREVIEW_MAX_BYTES",
    "ProviderInvalidResponseError",
    "ProviderRepresentation",
    "ProviderRepresentationAdapter",
    "ProviderUnavailableError",
    "RepresentationTooLargeError",
    "RepresentationUnavailableError",
    "ResourceAccessError",
    "ResourceAccessRepository",
    "ResourceAccessService",
    "ResourceAccessSource",
    "ResourceAccessUnavailableError",
    "ResourceNotFoundError",
    "ResourceRepresentation",
    "ResourceRepresentationDescriptor",
    "ResourceRepresentationKind",
    "ResourceVideo",
    "ResourceVideoDescriptor",
    "THUMBNAIL_MAX_BYTES",
    "UnsupportedRepresentationError",
]
