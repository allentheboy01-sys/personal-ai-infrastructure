from .adapter import NextcloudAdapter


_INCREMENTAL_EXPORTS = (
    "ACTIVITY_ENDPOINT",
    "ACTIVITY_PAGE_LIMIT",
    "NEXTCLOUD_INCREMENTAL_MECHANISM",
    "NextcloudActivityIncrementalSync",
    "NextcloudActivityUnavailableError",
    "NextcloudBootstrapRequiredError",
    "NextcloudTargetResolutionError",
    "decode_nextcloud_activity_checkpoint",
    "encode_nextcloud_activity_checkpoint",
)


def __getattr__(name: str):
    if name not in _INCREMENTAL_EXPORTS:
        raise AttributeError(name)
    from . import incremental

    return getattr(incremental, name)

__all__ = [
    "NextcloudAdapter",
    *_INCREMENTAL_EXPORTS,
]
