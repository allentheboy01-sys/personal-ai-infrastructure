from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Literal

from mcp.server import MCPServer
from pydantic import Field

from pdi.data_status import DataStatusError, DataStatusService
from pdi.query import InvalidQueryError, QueryError, QueryService
from pdi.resource_query import (
    ResourceQueryFilters,
    ResourceQueryPrimary,
    ResourceQueryService,
    ResourceQuerySort,
    ResourceQueryUnavailableError,
    serialize_resource_query_result,
)
from pdi.observation import ObservationError, ObservationService
from pdi.rich_retrieval import (
    RichFilters,
    RichPrimary,
    RichRetrievalError,
    RichRetrievalService,
)
from pdi.retrieval import (
    ProviderCapabilityUnavailableError,
    RetrievalError,
    RetrievalService,
)

from .serialization import (
    serialize_resource_aggregation,
    serialize_resource_detail,
    serialize_rich_retrieval_result,
    serialize_retrieval_result,
    serialize_resource_summary,
    serialize_statement,
    serialize_status_snapshot,
)


ToolResult = dict[str, object]


def _error_result(
    error: (
        QueryError
        | ObservationError
        | RetrievalError
        | RichRetrievalError
    ),
) -> ToolResult:
    return {
        "ok": False,
        "error": {
            "code": error.code,
            "message": str(error),
        },
    }


def _query_call(operation: Callable[[], ToolResult]) -> ToolResult:
    try:
        return operation()
    except (
        QueryError,
        ObservationError,
        RetrievalError,
        RichRetrievalError,
    ) as error:
        return _error_result(error)


def _datetime_argument(
    value: str | None,
    name: str,
) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise InvalidQueryError(
            f"{name} must be an ISO 8601 datetime"
        )
    try:
        return datetime.fromisoformat(value.strip())
    except ValueError as error:
        raise InvalidQueryError(
            f"{name} must be an ISO 8601 datetime"
        ) from error


def create_server(
    query_service: QueryService,
    observation_service: ObservationService | None = None,
    retrieval_service: RetrievalService | None = None,
    rich_retrieval_service: RichRetrievalService | None = None,
    data_status_service: DataStatusService | None = None,
    resource_query_service: ResourceQueryService | None = None,
) -> MCPServer:
    server = MCPServer(
        name="pdi-personal-retrieval",
        instructions=(
            "Read-only access to resource metadata stored by PDI. "
            "Do not describe PDI observation times as user or provider "
            "creation, upload, modification, or completion times."
        ),
    )

    @server.tool(structured_output=True)
    async def pdi_query_resources(
        primary: Annotated[
            ResourceQueryPrimary,
            Field(discriminator="kind"),
        ],
        filters: ResourceQueryFilters | None = None,
        sort: ResourceQuerySort | None = None,
        limit: int = 10,
        scan_limit: int = 500,
        continuable: bool = False,
        continuation: str | None = None,
    ) -> ToolResult:
        """Run one typed, deterministic, bounded Resource selection.

        The caller must choose exactly one primary; PDI performs no automatic
        cross-strategy fallback. Ordinary top-N requests should leave
        continuable=false and never page merely because more matches exist.
        provider_semantic currently requires explicit provider=immich.
        pdi_observed_at, file_modified_at, and captured_at are distinct time
        bases and are never substituted for one another.
        """

        def operation() -> ToolResult:
            if resource_query_service is None:
                raise ResourceQueryUnavailableError(
                    "Unified Resource query service is unavailable"
                )
            result = resource_query_service.query_resources(
                primary=primary,
                filters=filters,
                sort=sort,
                limit=limit,
                scan_limit=scan_limit,
                continuable=continuable,
                continuation=continuation,
            )
            return {
                "ok": True,
                **serialize_resource_query_result(result),
            }

        return _query_call(operation)

    @server.tool(structured_output=True)
    def pdi_list_recent_resources(
        days: int | None = None,
        provider: str | None = None,
        resource_type: str | None = None,
        mime_type: str | None = None,
        path_prefix: str | None = None,
        limit: int = 50,
        observed_from: str | None = None,
        observed_to: str | None = None,
        cursor: str | None = None,
        mime_category: str | None = None,
    ) -> ToolResult:
        """List resources recently first identified by PDI.

        The returned time represents when PDI first created the resource
        record. It does not prove when the user created, uploaded, modified,
        or completed the resource.
        """

        def operation() -> ToolResult:
            page = query_service.list_resource_page(
                days=days,
                observed_from=_datetime_argument(
                    observed_from,
                    "observed_from",
                ),
                observed_to=_datetime_argument(
                    observed_to,
                    "observed_to",
                ),
                provider=provider,
                resource_type=resource_type,
                mime_type=mime_type,
                mime_category=mime_category,
                path_prefix=path_prefix,
                limit=limit,
                cursor=cursor,
            )
            return {
                "ok": True,
                "resources": [
                    serialize_resource_summary(resource)
                    for resource in page.resources
                ],
                "next_cursor": page.next_cursor,
            }

        return _query_call(operation)

    @server.tool(structured_output=True)
    def pdi_search_resources(
        query: str,
        provider: str | None = None,
        resource_type: str | None = None,
        mime_type: str | None = None,
        path_prefix: str | None = None,
        limit: int = 50,
        observed_from: str | None = None,
        observed_to: str | None = None,
        cursor: str | None = None,
        mime_category: str | None = None,
    ) -> ToolResult:
        """Deterministically search PDI metadata and structured filters.

        Use for explicit filename, title, source path, metadata, or filter
        intent. After successful semantic retrieval, do not use this as an
        automatic fallback unless the user also requested metadata search.
        """

        def operation() -> ToolResult:
            page = query_service.search_resource_page(
                query=query,
                observed_from=_datetime_argument(
                    observed_from,
                    "observed_from",
                ),
                observed_to=_datetime_argument(
                    observed_to,
                    "observed_to",
                ),
                provider=provider,
                resource_type=resource_type,
                mime_type=mime_type,
                mime_category=mime_category,
                path_prefix=path_prefix,
                limit=limit,
                cursor=cursor,
            )
            return {
                "ok": True,
                "resources": [
                    serialize_resource_summary(resource)
                    for resource in page.resources
                ],
                "next_cursor": page.next_cursor,
            }

        return _query_call(operation)

    @server.tool(structured_output=True)
    def pdi_aggregate_resources(
        group_by: Literal[
            "provider",
            "day",
            "mime_type",
            "mime_category",
            "person_label",
        ]
        | None = None,
        observed_from: str | None = None,
        observed_to: str | None = None,
        provider: str | None = None,
        resource_type: str | None = None,
        mime_type: str | None = None,
        mime_category: str | None = None,
        path_prefix: str | None = None,
    ) -> ToolResult:
        """Count Resources or discover bounded current Person labels.

        Use group_by=person_label to discover active, Provider-declared Person
        labels before grounding a colloquial named-person request. That
        projection is deterministic, bounded, and accepts only the optional
        provider filter; it does not use Resource text, OCR, filenames, or
        semantic inference. Make at most one discovery call per user intent and
        reuse its buckets. Skip discovery when the user already supplied an
        exact Person label. Other groupings describe when PDI first recognized
        Resources; they do not describe capture, upload, user creation,
        provider creation, or provider modification time.
        """

        def operation() -> ToolResult:
            result = query_service.aggregate_resources(
                group_by=group_by,
                observed_from=_datetime_argument(
                    observed_from,
                    "observed_from",
                ),
                observed_to=_datetime_argument(
                    observed_to,
                    "observed_to",
                ),
                provider=provider,
                resource_type=resource_type,
                mime_type=mime_type,
                mime_category=mime_category,
                path_prefix=path_prefix,
            )
            return {
                "ok": True,
                **serialize_resource_aggregation(result),
            }

        return _query_call(operation)

    @server.tool(structured_output=True)
    def pdi_retrieve_resources(
        query: str,
        provider: Literal["immich"],
        limit: int = 20,
    ) -> ToolResult:
        """Use provider-native semantic retrieval to find PDI Resources.

        Use when the user describes resource content or visual concepts such
        as objects, scenes, environments, or document-like images. Results
        preserve provider ranking. A successful retrieval normally satisfies
        semantic-search intent; do not automatically follow it with metadata
        search unless the user requested both. V0.1 supports Immich only.
        """

        def operation() -> ToolResult:
            if retrieval_service is None:
                raise ProviderCapabilityUnavailableError(
                    "Provider retrieval service is unavailable"
                )
            result = retrieval_service.retrieve_resources(
                query=query,
                provider=provider,
                limit=limit,
            )
            return {
                "ok": True,
                **serialize_retrieval_result(result),
            }

        return _query_call(operation)

    @server.tool(structured_output=True)
    def pdi_rich_retrieve_resources(
        primary: Annotated[RichPrimary, Field(discriminator="kind")],
        filters: RichFilters | None = None,
        limit: int = 10,
    ) -> ToolResult:
        """Compose one bounded candidate source with deterministic filters.

        Call this tool directly, without first calling pdi_retrieve_resources,
        when one request combines a content or visual concept with a PDI
        filter or required signal. Use provider_semantic for that primary. To
        return only photos or images, set mime_category to image in that same
        call. To
        identify which semantic hits have OCR, require media.ocr_text;
        existence is reported in matched_predicates, so do not call
        observations per hit when existence is all the user asked for. To
        answer which concept hits have OCR, make exactly that one filtered
        call and treat its surviving hits as the answer; do not make an
        unfiltered comparison call. To return photo capture times, require
        media.captured_at or use captured_from/to; these filter media capture
        time. file_modified_from/to filter the Provider-reported file
        modification time. They are distinct and never fall back to each
        other or to PDI first-observed time. Matching hits include the
        structured captured_at or file_modified_at value when the signal is
        requested. Use observation_text for literal current OCR or
        document-excerpt substring matching. It directly finds matching
        Resources but does not return the body; fetch observations only for
        the small selected set when the user needs excerpt content. This does
        not merge candidate sources or return raw observation bodies. Use
        person_label for named-person requests and only with an exact current
        Provider-declared Person label. For explicit photo/image or video
        requests, set mime_category to image or video in the same call. It
        finds Resources through current PDI Resource-Person relations; it
        does not infer aliases, family relationships, or fuzzy matches. Once
        a correct person_label call returns non-empty type-appropriate hits,
        do not make speculative alias, semantic, metadata, or observation
        fallback calls for the same intent. An empty exact named-person result
        does not authorize semantic results as proof of Person membership.
        The optional provider on that primary restricts label provenance,
        while filters.provider continues to restrict Resource sources.
        Result limit defaults to 10 and must not exceed 20.
        """

        def operation() -> ToolResult:
            if rich_retrieval_service is None:
                raise ProviderCapabilityUnavailableError(
                    "Rich retrieval service is unavailable"
                )
            result = rich_retrieval_service.retrieve_resources(
                primary=primary,
                filters=filters,
                limit=limit,
            )
            return {
                "ok": True,
                **serialize_rich_retrieval_result(result),
            }

        return _query_call(operation)

    @server.tool(structured_output=True)
    def pdi_get_resource(resource_ref: str) -> ToolResult:
        """Get one PDI resource projection by its resource reference."""

        def operation() -> ToolResult:
            resource = query_service.get_resource(resource_ref)
            return {
                "ok": True,
                "resource": serialize_resource_detail(resource),
            }

        return _query_call(operation)

    @server.tool(structured_output=True)
    def pdi_get_resource_observations(
        resource_ref: str,
        predicate: str | None = None,
    ) -> ToolResult:
        """Get current typed observations for one PDI Resource.

        Observations are provenance-bearing claims made by a named generator;
        they are not a single universal truth or PDI first-observed time.
        """

        def operation() -> ToolResult:
            if observation_service is None:
                raise ObservationError(
                    "Observation service is unavailable"
                )
            statements = observation_service.get_resource_statements(
                resource_ref,
                predicate=predicate,
                include_history=False,
                limit=100,
            )
            return {
                "ok": True,
                "observations": [
                    serialize_statement(statement)
                    for statement in statements
                ],
            }

        return _query_call(operation)

    @server.tool(structured_output=True)
    def pdi_get_data_status() -> ToolResult:
        """Report PDI data-pipeline execution and objective freshness signals.

        This does not report CPU, disk, Docker, network, systemd/service
        health, or live Provider state. A Provider sync success means PDI last
        completed its observation/sync; it does not guarantee the Provider is
        currently identical to PDI. Dependency validation only means the
        latest successful dependent execution happened at or after every
        latest upstream success; it does not mean fresh=true.
        """
        if data_status_service is None:
            return {
                "ok": False,
                "error": {
                    "code": "data_status_unavailable",
                    "message": "PDI data status service is unavailable",
                },
            }
        try:
            snapshot = data_status_service.get_status()
        except DataStatusError as error:
            return {
                "ok": False,
                "error": {
                    "code": error.code,
                    "message": str(error),
                },
            }
        return {"ok": True, **serialize_status_snapshot(snapshot)}

    return server
