from types import MappingProxyType

import pytest

from pdi.observation import (
    Evidence,
    EvidenceSourceKind,
    ObservationValidationError,
    PredicateCardinality,
    PredicateDefinition,
    StatementDraft,
    StatementValueType,
    TypedStatementValue,
)
from pdi.observation.models import _validate_statement_set


DEFINITION = PredicateDefinition(
    "test.multi",
    StatementValueType.STRING,
    PredicateCardinality.MULTI,
)


def _draft(value: str) -> StatementDraft:
    return StatementDraft(
        "test.multi",
        TypedStatementValue(StatementValueType.STRING, value),
        Evidence(EvidenceSourceKind.RESOURCE_CONTENT, "test.locator"),
    )


def test_multi_set_accepts_order_independent_unique_values() -> None:
    registry = MappingProxyType({"test.multi": DEFINITION})
    _validate_statement_set(registry, (_draft("B"), _draft("A")))
    _validate_statement_set(registry, (_draft("A"),))


def test_multi_set_rejects_duplicate_values() -> None:
    with pytest.raises(ObservationValidationError):
        _validate_statement_set(
            {"test.multi": DEFINITION},
            (_draft("A"), _draft("A")),
        )
