import pytest

from pdi.decision import Action, ActionType, Decision
from pdi.models import AssetSource
from pdi.models.asset_source import POSTGRES_BIGINT_MAX
from pdi.repository import InMemoryRepository


def test_in_memory_source_observations_round_trip() -> None:
    repository = InMemoryRepository()
    source = AssetSource(
        blob_id="blob-id",
        provider="test-provider",
        external_id="source-id",
        provider_mime_type="text/markdown",
        provider_size=321,
    )
    repository.execute(
        Decision(
            actions=[
                Action(
                    type=ActionType.CREATE_SOURCE,
                    source=source,
                )
            ]
        )
    )

    stored = repository.find_source("test-provider", "source-id")

    assert stored == source
    assert stored.provider_mime_type == "text/markdown"
    assert stored.provider_size == 321


def test_legacy_source_without_observations_remains_valid() -> None:
    source = AssetSource(
        blob_id="blob-id",
        provider="test-provider",
        external_id="legacy-source",
    )

    assert source.provider_mime_type is None
    assert source.provider_size is None


@pytest.mark.parametrize(
    "provider_size",
    [None, 0, POSTGRES_BIGINT_MAX],
)
def test_source_accepts_valid_provider_size(
    provider_size: int | None,
) -> None:
    source = AssetSource(provider_size=provider_size)

    assert source.provider_size == provider_size


@pytest.mark.parametrize(
    "provider_size",
    [True, -1, POSTGRES_BIGINT_MAX + 1, 1.5, "1", object()],
)
def test_source_rejects_invalid_provider_size(
    provider_size: object,
) -> None:
    with pytest.raises(ValueError, match="provider_size"):
        AssetSource(provider_size=provider_size)  # type: ignore[arg-type]
