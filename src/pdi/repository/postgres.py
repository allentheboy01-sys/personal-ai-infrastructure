from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Engine, case, func, or_, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.sql.elements import ColumnElement

from pdi.decision import Action, ActionType, Decision
from pdi.models import Asset, AssetSource, Blob
from pdi.query.models import (
    AssetDetail,
    AssetSummary,
    BlobView,
    SourceView,
)
from pdi.query.repository import QueryRepository
from pdi.query.resources import (
    ContentSummary,
    RecentResourcesQuery,
    RESOURCE_TIME_BASIS,
    ResourceAggregationBucket,
    ResourceAggregationQuery,
    ResourceAggregationResult,
    ResourceDetail,
    ResourceFilters,
    ResourceGroupBy,
    ResourceListPageQuery,
    ResourceSearchQuery,
    ResourceSearchPageQuery,
    ResourceSourceSummary,
    ResourceSummary,
    ResourceTimeRange,
    format_resource_ref,
)
from pdi.rich_retrieval import (
    InvalidRichRetrievalStateError,
    ObservationTextPrimary,
    RichCandidate,
    RichFilterSignals,
    RichFilters,
    RichRetrievalRepository,
)
from pdi.retrieval import (
    RetrievalMappingError,
    RetrievalMappingRepository,
)
from pdi.repository.base import Repository
from pdi.repository.orm.asset import AssetORM
from pdi.repository.orm.asset_source import AssetSourceORM
from pdi.repository.orm.blob import BlobORM
from pdi.repository.orm.observation import ResourceStatementORM


class PostgreSQLRepository(
    Repository,
    QueryRepository,
    RetrievalMappingRepository,
    RichRetrievalRepository,
):
    def __init__(
        self,
        engine: Engine,
    ) -> None:
        self._session_factory = sessionmaker(
            bind=engine,
            class_=Session,
            expire_on_commit=False,
        )

    def test_connection(self) -> bool:
        """验证 Repository 是否能够访问数据库。"""
        with self._session_factory() as session:
            result = session.execute(text("SELECT 1"))
            return result.scalar_one() == 1

    @staticmethod
    def _asset_to_orm(
        asset: Asset,
    ) -> AssetORM:
        return AssetORM(
            id=UUID(asset.id),
            title=asset.title,
            metadata_=asset.metadata,
            created_at=asset.created_at,
            updated_at=asset.updated_at,
        )

    @staticmethod
    def _asset_to_domain(
        asset_orm: AssetORM,
    ) -> Asset:
        return Asset(
            id=str(asset_orm.id),
            title=asset_orm.title,
            metadata=dict(asset_orm.metadata_),
            created_at=asset_orm.created_at,
            updated_at=asset_orm.updated_at,
        )

    @staticmethod
    def _asset_to_summary(
        asset_orm: AssetORM,
    ) -> AssetSummary:
        return AssetSummary(
            id=str(asset_orm.id),
            title=asset_orm.title,
            created_at=asset_orm.created_at,
            updated_at=asset_orm.updated_at,
        )

    @staticmethod
    def _blob_to_orm(
        blob: Blob,
    ) -> BlobORM:
        return BlobORM(
            id=UUID(blob.id),
            asset_id=UUID(blob.asset_id),
            hash=blob.hash,
            size=blob.size,
            mime_type=blob.mime_type,
        )

    @staticmethod
    def _blob_to_domain(
        blob_orm: BlobORM,
    ) -> Blob:
        return Blob(
            id=str(blob_orm.id),
            asset_id=str(blob_orm.asset_id),
            hash=blob_orm.hash,
            size=blob_orm.size,
            mime_type=blob_orm.mime_type,
        )

    @staticmethod
    def _blob_to_view(
        blob_orm: BlobORM,
    ) -> BlobView:
        return BlobView(
            id=str(blob_orm.id),
            asset_id=str(blob_orm.asset_id),
            hash=blob_orm.hash,
            size=blob_orm.size,
            mime_type=blob_orm.mime_type,
        )

    @staticmethod
    def _asset_source_to_orm(
        source: AssetSource,
    ) -> AssetSourceORM:
        if source.blob_id is None:
            raise ValueError(
                "AssetSource requires blob_id"
            )

        return AssetSourceORM(
            id=UUID(source.id),
            blob_id=UUID(source.blob_id),
            provider=source.provider,
            external_id=source.external_id,
            path=source.path,
            name=source.name,
            version_tag=source.version_tag,
            metadata_=source.metadata,
            is_active=source.is_active,
            deleted_at=source.deleted_at,
        )

    @staticmethod
    def _asset_source_to_domain(
        source_orm: AssetSourceORM,
    ) -> AssetSource:
        return AssetSource(
            id=str(source_orm.id),
            blob_id=str(source_orm.blob_id),
            provider=source_orm.provider,
            external_id=source_orm.external_id,
            path=source_orm.path,
            name=source_orm.name,
            version_tag=source_orm.version_tag,
            metadata=dict(source_orm.metadata_),
            is_active=source_orm.is_active,
            deleted_at=source_orm.deleted_at,
        )

    @staticmethod
    def _asset_source_to_view(
        source_orm: AssetSourceORM,
    ) -> SourceView:
        return SourceView(
            id=str(source_orm.id),
            blob_id=str(source_orm.blob_id),
            provider=source_orm.provider,
            external_id=source_orm.external_id,
            path=source_orm.path,
            name=source_orm.name,
            version_tag=source_orm.version_tag,
            metadata=dict(source_orm.metadata_),
            is_active=source_orm.is_active,
            deleted_at=source_orm.deleted_at,
        )

    def find_source(
        self,
        provider: str,
        external_id: str,
    ) -> AssetSource | None:
        with self._session_factory() as session:
            statement = (
                select(AssetSourceORM)
                .where(
                    AssetSourceORM.provider == provider,
                    AssetSourceORM.external_id == external_id,
                )
            )

            source_orm = (
                session.execute(statement)
                .scalar_one_or_none()
            )

            if source_orm is None:
                return None

            return self._asset_source_to_domain(source_orm)

    def list_active_sources(
        self,
        provider: str,
    ) -> list[AssetSource]:
        with self._session_factory() as session:
            statement = (
                select(AssetSourceORM)
                .where(
                    AssetSourceORM.provider == provider,
                    AssetSourceORM.is_active.is_(True),
                )
            )

            source_orms = (
                session.execute(statement)
                .scalars()
                .all()
            )

            return [
                self._asset_source_to_domain(source_orm)
                for source_orm in source_orms
            ]

    def find_blob_by_hash(
        self,
        content_hash: str,
    ) -> Blob | None:
        with self._session_factory() as session:
            statement = (
                select(BlobORM)
                .where(
                    BlobORM.hash == content_hash,
                )
            )

            blob_orm = (
                session.execute(statement)
                .scalar_one_or_none()
            )

            if blob_orm is None:
                return None

            return self._blob_to_domain(blob_orm)

    def find_blob_by_hash_in_asset(
        self,
        content_hash: str,
        asset_id: str,
    ) -> Blob | None:
        with self._session_factory() as session:
            statement = (
                select(BlobORM)
                .where(
                    BlobORM.asset_id == UUID(asset_id),
                    BlobORM.hash == content_hash,
                )
            )

            blob_orm = (
                session.execute(statement)
                .scalar_one_or_none()
            )

            if blob_orm is None:
                return None

            return self._blob_to_domain(blob_orm)

    def get_blob(
        self,
        blob_id: str,
    ) -> Blob | None:
        with self._session_factory() as session:
            statement = (
                select(BlobORM)
                .where(
                    BlobORM.id == UUID(blob_id),
                )
            )

            blob_orm = (
                session.execute(statement)
                .scalar_one_or_none()
            )

            if blob_orm is None:
                return None

            return self._blob_to_domain(blob_orm)

    def get_asset(
        self,
        asset_id: str,
    ) -> Asset | None:
        with self._session_factory() as session:
            statement = (
                select(AssetORM)
                .where(
                    AssetORM.id == UUID(asset_id),
                )
            )

            asset_orm = (
                session.execute(statement)
                .scalar_one_or_none()
            )

            if asset_orm is None:
                return None

            return self._asset_to_domain(asset_orm)

    def list_asset_summaries(
        self,
    ) -> tuple[AssetSummary, ...]:
        with self._session_factory() as session:
            asset_orms = (
                session.execute(
                    select(AssetORM).order_by(
                        AssetORM.id.asc(),
                    )
                )
                .scalars()
                .all()
            )

            return tuple(
                self._asset_to_summary(asset_orm)
                for asset_orm in asset_orms
            )

    def get_asset_detail(
        self,
        asset_id: str,
    ) -> AssetDetail | None:
        with self._session_factory() as session:
            asset_orm = session.get(
                AssetORM,
                UUID(asset_id),
            )

            if asset_orm is None:
                return None

            blob_orms = (
                session.execute(
                    select(BlobORM).where(
                        BlobORM.asset_id == asset_orm.id,
                    ).order_by(
                        BlobORM.id.asc(),
                    )
                )
                .scalars()
                .all()
            )

            source_orms: list[AssetSourceORM] = []

            if blob_orms:
                source_orms = list(
                    session.execute(
                        select(AssetSourceORM).where(
                            AssetSourceORM.blob_id.in_(
                                [
                                    blob_orm.id
                                    for blob_orm in blob_orms
                                ]
                            )
                        ).order_by(
                            AssetSourceORM.id.asc(),
                        )
                    )
                    .scalars()
                    .all()
                )

            return AssetDetail(
                id=str(asset_orm.id),
                title=asset_orm.title,
                metadata=dict(asset_orm.metadata_),
                created_at=asset_orm.created_at,
                updated_at=asset_orm.updated_at,
                blobs=tuple(
                    self._blob_to_view(blob_orm)
                    for blob_orm in blob_orms
                ),
                sources=tuple(
                    self._asset_source_to_view(source_orm)
                    for source_orm in source_orms
                ),
            )

    @staticmethod
    def _escape_like(value: str) -> str:
        return (
            value.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )

    @classmethod
    def _source_filters(
        cls,
        *,
        provider: str | None,
        mime_type: str | None,
        mime_category: str | None,
        path_prefix: str | None,
    ) -> list[ColumnElement[bool]]:
        filters = [AssetSourceORM.is_active.is_(True)]

        if provider is not None:
            filters.append(AssetSourceORM.provider == provider)
        if mime_type is not None:
            filters.append(BlobORM.mime_type == mime_type)
        if mime_category is not None:
            filters.append(
                cls._mime_category_expression() == mime_category
            )
        if path_prefix is not None:
            escaped_prefix = cls._escape_like(path_prefix)
            filters.append(
                AssetSourceORM.path.ilike(
                    f"{escaped_prefix}%",
                    escape="\\",
                )
            )

        return filters

    @staticmethod
    def _mime_category_expression():
        return case(
            (
                or_(
                    BlobORM.mime_type.is_(None),
                    BlobORM.mime_type == "",
                ),
                "unknown",
            ),
            (
                func.strpos(BlobORM.mime_type, "/") > 0,
                func.lower(
                    func.split_part(BlobORM.mime_type, "/", 1)
                ),
            ),
            else_="other",
        )

    @classmethod
    def _active_source_exists(
        cls,
        *,
        provider: str | None,
        mime_type: str | None,
        mime_category: str | None,
        path_prefix: str | None,
        search_text: str | None = None,
    ) -> ColumnElement[bool]:
        filters = cls._source_filters(
            provider=provider,
            mime_type=mime_type,
            mime_category=mime_category,
            path_prefix=path_prefix,
        )

        if search_text is not None:
            escaped_text = cls._escape_like(search_text)
            pattern = f"%{escaped_text}%"
            filters.append(
                or_(
                    AssetSourceORM.name.ilike(
                        pattern,
                        escape="\\",
                    ),
                    AssetSourceORM.path.ilike(
                        pattern,
                        escape="\\",
                    ),
                )
            )

        return (
            select(1)
            .select_from(AssetSourceORM)
            .join(
                BlobORM,
                AssetSourceORM.blob_id == BlobORM.id,
            )
            .where(
                BlobORM.asset_id == AssetORM.id,
                *filters,
            )
            .correlate(AssetORM)
            .exists()
        )

    @staticmethod
    def _resource_source_summary(
        source_orm: AssetSourceORM,
        blob_orm: BlobORM,
    ) -> ResourceSourceSummary:
        return ResourceSourceSummary(
            provider=source_orm.provider,
            location=source_orm.path,
            name=source_orm.name,
            mime_type=blob_orm.mime_type,
            size_bytes=blob_orm.size,
            is_active=source_orm.is_active,
        )

    @classmethod
    def _resource_summary(
        cls,
        asset_orm: AssetORM,
        source_orms: list[AssetSourceORM],
        blobs_by_id: dict[UUID, BlobORM],
    ) -> ResourceSummary:
        ordered_sources = sorted(
            source_orms,
            key=lambda source: (
                source.provider,
                source.path or "",
                source.name or "",
                source.external_id,
            ),
        )
        return ResourceSummary(
            resource_ref=format_resource_ref(asset_orm.id),
            resource_type="file",
            display_name=asset_orm.title,
            pdi_first_observed_at=asset_orm.created_at,
            sources=tuple(
                cls._resource_source_summary(
                    source,
                    blobs_by_id[source.blob_id],
                )
                for source in ordered_sources
            ),
        )

    def _load_resource_summaries(
        self,
        session: Session,
        asset_orms: list[AssetORM],
    ) -> tuple[ResourceSummary, ...]:
        if not asset_orms:
            return ()

        asset_ids = [asset.id for asset in asset_orms]
        blob_orms = list(
            session.execute(
                select(BlobORM).where(
                    BlobORM.asset_id.in_(asset_ids)
                )
            )
            .scalars()
            .all()
        )
        blobs_by_id = {blob.id: blob for blob in blob_orms}
        source_orms: list[AssetSourceORM] = []

        if blobs_by_id:
            source_orms = list(
                session.execute(
                    select(AssetSourceORM).where(
                        AssetSourceORM.blob_id.in_(blobs_by_id),
                        AssetSourceORM.is_active.is_(True),
                    )
                )
                .scalars()
                .all()
            )

        sources_by_asset_id: dict[UUID, list[AssetSourceORM]] = {
            asset_id: [] for asset_id in asset_ids
        }
        for source in source_orms:
            blob = blobs_by_id[source.blob_id]
            sources_by_asset_id[blob.asset_id].append(source)

        return tuple(
            self._resource_summary(
                asset,
                sources_by_asset_id[asset.id],
                blobs_by_id,
            )
            for asset in asset_orms
        )

    def map_active_resources(
        self,
        *,
        provider: str,
        provider_locators: tuple[str, ...],
    ) -> dict[str, tuple[ResourceSummary, ...]]:
        unique_locators = tuple(dict.fromkeys(provider_locators))
        if not unique_locators:
            return {}

        with self._session_factory() as session:
            rows = session.execute(
                select(AssetSourceORM, BlobORM, AssetORM)
                .select_from(AssetSourceORM)
                .outerjoin(
                    BlobORM,
                    AssetSourceORM.blob_id == BlobORM.id,
                )
                .outerjoin(
                    AssetORM,
                    BlobORM.asset_id == AssetORM.id,
                )
                .where(
                    AssetSourceORM.provider == provider,
                    AssetSourceORM.external_id.in_(unique_locators),
                    AssetSourceORM.is_active.is_(True),
                )
            ).all()

            assets_by_id: dict[UUID, AssetORM] = {}
            asset_ids_by_locator: dict[str, list[UUID]] = {}
            for source_orm, blob_orm, asset_orm in rows:
                if blob_orm is None or asset_orm is None:
                    raise RetrievalMappingError(
                        "Active Provider source has a broken PDI mapping"
                    )
                assets_by_id[asset_orm.id] = asset_orm
                asset_ids_by_locator.setdefault(
                    source_orm.external_id,
                    [],
                ).append(asset_orm.id)

            summaries = self._load_resource_summaries(
                session,
                list(assets_by_id.values()),
            )
            summaries_by_asset_id = {
                UUID(summary.resource_ref.removeprefix("pdi:resource:")):
                summary
                for summary in summaries
            }

            return {
                locator: tuple(
                    summaries_by_asset_id[asset_id]
                    for asset_id in asset_ids
                )
                for locator, asset_ids in asset_ids_by_locator.items()
            }

    def search_current_observation_text(
        self,
        *,
        primary: ObservationTextPrimary,
        limit: int,
    ) -> tuple[RichCandidate, ...]:
        pattern = f"%{self._escape_like(primary.query)}%"
        with self._session_factory() as session:
            asset_orms = list(
                session.execute(
                    select(AssetORM)
                    .join(
                        ResourceStatementORM,
                        ResourceStatementORM.subject_asset_id
                        == AssetORM.id,
                    )
                    .where(
                        ResourceStatementORM.predicate
                        == primary.predicate,
                        ResourceStatementORM.value_type == "string",
                        ResourceStatementORM.is_current.is_(True),
                        ResourceStatementORM.string_value.ilike(
                            pattern,
                            escape="\\",
                        ),
                        self._active_source_exists(
                            provider=None,
                            mime_type=None,
                            mime_category=None,
                            path_prefix=None,
                        ),
                    )
                    .distinct()
                    .order_by(
                        AssetORM.title.asc(),
                        AssetORM.id.asc(),
                    )
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            summaries = self._load_resource_summaries(
                session,
                asset_orms,
            )
        return tuple(
            RichCandidate(
                resource=resource,
                source_rank=rank,
                matched_predicates=(primary.predicate,),
            )
            for rank, resource in enumerate(summaries, start=1)
        )

    def load_rich_filter_signals(
        self,
        *,
        resource_refs: tuple[str, ...],
        filters: RichFilters,
    ) -> dict[str, RichFilterSignals]:
        unique_refs = tuple(dict.fromkeys(resource_refs))
        if not unique_refs:
            return {}
        asset_ids_by_ref = {
            resource_ref: UUID(
                resource_ref.removeprefix("pdi:resource:")
            )
            for resource_ref in unique_refs
        }
        asset_ids = tuple(asset_ids_by_ref.values())
        source_filter_requested = any((
            filters.provider,
            filters.mime_type,
            filters.mime_category,
            filters.path_prefix,
        ))
        observation_predicates = tuple(dict.fromkeys((
            *filters.required_predicates,
            *(
                ("media.captured_at",)
                if (
                    filters.captured_from is not None
                    or filters.captured_to is not None
                )
                else ()
            ),
        )))

        eligible_asset_ids = set(asset_ids)
        current_predicates: dict[UUID, set[str]] = {
            asset_id: set() for asset_id in asset_ids
        }
        captured_values: dict[UUID, list[datetime]] = {
            asset_id: [] for asset_id in asset_ids
        }

        with self._session_factory() as session:
            if source_filter_requested:
                eligible_asset_ids = set(
                    session.execute(
                        select(BlobORM.asset_id)
                        .select_from(BlobORM)
                        .join(
                            AssetSourceORM,
                            AssetSourceORM.blob_id == BlobORM.id,
                        )
                        .where(
                            BlobORM.asset_id.in_(asset_ids),
                            *self._source_filters(
                                provider=filters.provider,
                                mime_type=filters.mime_type,
                                mime_category=filters.mime_category,
                                path_prefix=filters.path_prefix,
                            ),
                        )
                        .distinct()
                    ).scalars()
                )

            if observation_predicates:
                rows = session.execute(
                    select(
                        ResourceStatementORM.subject_asset_id,
                        ResourceStatementORM.predicate,
                        ResourceStatementORM.value_type,
                        ResourceStatementORM.datetime_value,
                    ).where(
                        ResourceStatementORM.subject_asset_id.in_(
                            asset_ids
                        ),
                        ResourceStatementORM.predicate.in_(
                            observation_predicates
                        ),
                        ResourceStatementORM.is_current.is_(True),
                    )
                ).all()
                for (
                    asset_id,
                    predicate,
                    value_type,
                    datetime_value,
                ) in rows:
                    current_predicates[asset_id].add(predicate)
                    if predicate == "media.captured_at":
                        if (
                            value_type != "datetime"
                            or datetime_value is None
                        ):
                            raise InvalidRichRetrievalStateError(
                                "Current media.captured_at has an invalid "
                                "typed value"
                            )
                        captured_values[asset_id].append(datetime_value)

        for values in captured_values.values():
            if len(values) > 1:
                raise InvalidRichRetrievalStateError(
                    "Resource has multiple current media.captured_at "
                    "claims"
                )

        return {
            resource_ref: RichFilterSignals(
                resource_ref=resource_ref,
                source_metadata_match=(
                    asset_id in eligible_asset_ids
                ),
                captured_at=(
                    captured_values[asset_id][0]
                    if captured_values[asset_id]
                    else None
                ),
                current_predicates=frozenset(
                    current_predicates[asset_id]
                ),
            )
            for resource_ref, asset_id in asset_ids_by_ref.items()
        }

    @staticmethod
    def _asset_time_filters(
        *,
        observed_from,
        observed_to,
        snapshot_to=None,
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = []
        if observed_from is not None:
            filters.append(AssetORM.created_at >= observed_from)
        if observed_to is not None:
            filters.append(AssetORM.created_at < observed_to)
        if snapshot_to is not None:
            filters.append(AssetORM.created_at < snapshot_to)
        return filters

    @classmethod
    def _eligible_source_for_filters(
        cls,
        filters: ResourceFilters,
        *,
        search_text: str | None = None,
    ) -> ColumnElement[bool]:
        return cls._active_source_exists(
            provider=filters.provider,
            mime_type=filters.mime_type,
            mime_category=filters.mime_category,
            path_prefix=filters.path_prefix,
            search_text=search_text,
        )

    def list_resource_page(
        self,
        query: ResourceListPageQuery,
    ) -> tuple[ResourceSummary, ...]:
        eligible_source = self._eligible_source_for_filters(
            query.filters
        )
        filters = self._asset_time_filters(
            observed_from=query.time_range.observed_from,
            observed_to=query.time_range.observed_to,
            snapshot_to=query.snapshot_to,
        )
        if query.after_observed_at is not None:
            if query.after_asset_id is None:
                raise ValueError(
                    "Recent page position requires asset identity"
                )
            filters.append(
                or_(
                    AssetORM.created_at < query.after_observed_at,
                    (
                        (AssetORM.created_at == query.after_observed_at)
                        & (AssetORM.id > UUID(query.after_asset_id))
                    ),
                )
            )

        with self._session_factory() as session:
            asset_orms = list(
                session.execute(
                    select(AssetORM)
                    .where(
                        *filters,
                        eligible_source,
                    )
                    .order_by(
                        AssetORM.created_at.desc(),
                        AssetORM.id.asc(),
                    )
                    .limit(query.limit)
                )
                .scalars()
                .all()
            )
            return self._load_resource_summaries(session, asset_orms)

    def search_resource_page(
        self,
        query: ResourceSearchPageQuery,
    ) -> tuple[ResourceSummary, ...]:
        eligible_source = self._eligible_source_for_filters(
            query.filters
        )
        matching_source = self._eligible_source_for_filters(
            query.filters,
            search_text=query.query,
        )
        title_pattern = f"%{self._escape_like(query.query)}%"
        filters = self._asset_time_filters(
            observed_from=query.time_range.observed_from,
            observed_to=query.time_range.observed_to,
            snapshot_to=query.snapshot_to,
        )
        if query.after_title is not None:
            if query.after_asset_id is None:
                raise ValueError(
                    "Search page position requires asset identity"
                )
            filters.append(
                or_(
                    AssetORM.title > query.after_title,
                    (
                        (AssetORM.title == query.after_title)
                        & (AssetORM.id > UUID(query.after_asset_id))
                    ),
                )
            )

        with self._session_factory() as session:
            asset_orms = list(
                session.execute(
                    select(AssetORM)
                    .where(
                        *filters,
                        eligible_source,
                        or_(
                            AssetORM.title.ilike(
                                title_pattern,
                                escape="\\",
                            ),
                            matching_source,
                        ),
                    )
                    .order_by(
                        AssetORM.title.asc(),
                        AssetORM.id.asc(),
                    )
                    .limit(query.limit)
                )
                .scalars()
                .all()
            )
            return self._load_resource_summaries(session, asset_orms)

    def aggregate_resources(
        self,
        query: ResourceAggregationQuery,
    ) -> ResourceAggregationResult:
        source_filters = self._source_filters(
            provider=query.filters.provider,
            mime_type=query.filters.mime_type,
            mime_category=query.filters.mime_category,
            path_prefix=query.filters.path_prefix,
        )
        time_filters = self._asset_time_filters(
            observed_from=query.time_range.observed_from,
            observed_to=query.time_range.observed_to,
        )

        with self._session_factory() as session:
            if query.group_by is None:
                eligible_assets = (
                    select(AssetORM.id.label("asset_id"))
                    .select_from(AssetORM)
                    .join(BlobORM, BlobORM.asset_id == AssetORM.id)
                    .join(
                        AssetSourceORM,
                        AssetSourceORM.blob_id == BlobORM.id,
                    )
                    .where(*time_filters, *source_filters)
                    .distinct()
                    .subquery()
                )
                total_count = session.execute(
                    select(func.count()).select_from(eligible_assets)
                ).scalar_one()
                return ResourceAggregationResult(
                    time_basis=RESOURCE_TIME_BASIS,
                    time_range=query.time_range,
                    applied_filters=query.filters,
                    group_by=None,
                    total_count=total_count,
                    buckets=(),
                    buckets_truncated=False,
                )

            bucket_expression = self._aggregation_bucket_expression(
                query.group_by
            )
            resource_buckets = (
                select(
                    AssetORM.id.label("asset_id"),
                    bucket_expression.label("bucket"),
                )
                .select_from(AssetORM)
                .join(BlobORM, BlobORM.asset_id == AssetORM.id)
                .join(
                    AssetSourceORM,
                    AssetSourceORM.blob_id == BlobORM.id,
                )
                .where(*time_filters, *source_filters)
                .distinct()
                .subquery()
            )
            total_count_query = (
                select(
                    func.count(
                        func.distinct(resource_buckets.c.asset_id)
                    )
                )
                .select_from(resource_buckets)
                .correlate(None)
                .scalar_subquery()
            )
            bucket_count = func.count().label("bucket_count")
            statement = (
                select(
                    resource_buckets.c.bucket,
                    bucket_count,
                    total_count_query.label("total_count"),
                )
                .group_by(resource_buckets.c.bucket)
            )
            if query.group_by is ResourceGroupBy.DAY:
                statement = statement.order_by(
                    resource_buckets.c.bucket.asc()
                )
            else:
                statement = statement.order_by(
                    bucket_count.desc(),
                    resource_buckets.c.bucket.asc(),
                )
            rows = session.execute(
                statement.limit(query.bucket_limit + 1)
            ).all()

            buckets_truncated = len(rows) > query.bucket_limit
            visible_rows = rows[: query.bucket_limit]
            total_count = 0 if not rows else rows[0].total_count
            return ResourceAggregationResult(
                time_basis=RESOURCE_TIME_BASIS,
                time_range=query.time_range,
                applied_filters=query.filters,
                group_by=query.group_by,
                total_count=total_count,
                buckets=tuple(
                    ResourceAggregationBucket(
                        key=row.bucket,
                        count=row.bucket_count,
                    )
                    for row in visible_rows
                ),
                buckets_truncated=buckets_truncated,
            )

    @classmethod
    def _aggregation_bucket_expression(
        cls,
        group_by: ResourceGroupBy,
    ):
        if group_by is ResourceGroupBy.PROVIDER:
            return AssetSourceORM.provider
        if group_by is ResourceGroupBy.DAY:
            return func.to_char(
                func.timezone("UTC", AssetORM.created_at),
                "YYYY-MM-DD",
            )
        if group_by is ResourceGroupBy.MIME_TYPE:
            return case(
                (
                    or_(
                        BlobORM.mime_type.is_(None),
                        BlobORM.mime_type == "",
                    ),
                    "unknown",
                ),
                else_=BlobORM.mime_type,
            )
        if group_by is ResourceGroupBy.MIME_CATEGORY:
            return cls._mime_category_expression()
        raise ValueError(f"Unsupported group_by: {group_by}")

    def list_recent_resources(
        self,
        query: RecentResourcesQuery,
    ) -> tuple[ResourceSummary, ...]:
        return self.list_resource_page(
            ResourceListPageQuery(
                time_range=ResourceTimeRange(
                    observed_from=query.created_since,
                    observed_to=None,
                ),
                filters=ResourceFilters(
                    provider=query.provider,
                    resource_type=query.resource_type,
                    mime_type=query.mime_type,
                    mime_category=None,
                    path_prefix=query.path_prefix,
                ),
                snapshot_to=datetime.max.replace(tzinfo=UTC),
                after_observed_at=None,
                after_asset_id=None,
                limit=query.limit,
            )
        )

    def search_resources(
        self,
        query: ResourceSearchQuery,
    ) -> tuple[ResourceSummary, ...]:
        return self.search_resource_page(
            ResourceSearchPageQuery(
                query=query.query,
                time_range=ResourceTimeRange(
                    observed_from=None,
                    observed_to=None,
                ),
                filters=ResourceFilters(
                    provider=query.provider,
                    resource_type=query.resource_type,
                    mime_type=query.mime_type,
                    mime_category=None,
                    path_prefix=query.path_prefix,
                ),
                snapshot_to=datetime.max.replace(tzinfo=UTC),
                after_title=None,
                after_asset_id=None,
                limit=query.limit,
            )
        )

    def get_resource_detail(
        self,
        asset_id: str,
    ) -> ResourceDetail | None:
        with self._session_factory() as session:
            asset_orm = session.get(AssetORM, UUID(asset_id))

            if asset_orm is None:
                return None

            blob_orms = list(
                session.execute(
                    select(BlobORM).where(
                        BlobORM.asset_id == asset_orm.id
                    )
                )
                .scalars()
                .all()
            )
            blobs_by_id = {blob.id: blob for blob in blob_orms}
            source_orms: list[AssetSourceORM] = []

            if blobs_by_id:
                source_orms = list(
                    session.execute(
                        select(AssetSourceORM).where(
                            AssetSourceORM.blob_id.in_(blobs_by_id)
                        )
                    )
                    .scalars()
                    .all()
                )

            summary = self._resource_summary(
                asset_orm,
                source_orms,
                blobs_by_id,
            )
            ordered_blobs = sorted(
                blob_orms,
                key=lambda blob: (
                    blob.hash,
                    blob.mime_type or "",
                    blob.size if blob.size is not None else -1,
                ),
            )

            return ResourceDetail(
                resource_ref=summary.resource_ref,
                resource_type=summary.resource_type,
                display_name=summary.display_name,
                pdi_first_observed_at=summary.pdi_first_observed_at,
                sources=summary.sources,
                content_variants=tuple(
                    ContentSummary(
                        mime_type=blob.mime_type,
                        size_bytes=blob.size,
                        checksum=blob.hash,
                    )
                    for blob in ordered_blobs
                ),
            )

    def execute(
        self,
        decision: Decision,
    ) -> None:
        with self._session_factory() as session:
            try:
                for action in decision.actions:
                    match action.type:
                        case ActionType.CREATE_ASSET:
                            self._execute_create_asset(
                                session,
                                action,
                            )

                        case ActionType.CREATE_BLOB:
                            self._execute_create_blob(
                                session,
                                action,
                            )

                        case ActionType.CREATE_SOURCE:
                            self._execute_create_source(
                                session,
                                action,
                            )

                        case ActionType.UPDATE_SOURCE:
                            self._execute_update_source(
                                session,
                                action,
                            )

                        case ActionType.DEACTIVATE_SOURCE:
                            self._execute_deactivate_source(
                                session,
                                action,
                            )

                        case _:
                            raise ValueError(
                                f"Unsupported action type: "
                                f"{action.type}"
                            )

                    # 将当前 Action 写入数据库，
                    # 但仍然不提交整个事务。
                    session.flush()

                session.commit()

            except Exception:
                session.rollback()
                raise

    def _execute_create_asset(
        self,
        session: Session,
        action: Action,
    ) -> None:
        if action.asset is None:
            raise ValueError(
                "CREATE_ASSET requires asset"
            )

        asset_orm = self._asset_to_orm(
            action.asset
        )

        session.add(asset_orm)

    def _execute_create_blob(
        self,
        session: Session,
        action: Action,
    ) -> None:
        if action.blob is None:
            raise ValueError(
                "CREATE_BLOB requires blob"
            )

        blob_orm = self._blob_to_orm(
            action.blob
        )

        session.add(blob_orm)

    def _execute_create_source(
        self,
        session: Session,
        action: Action,
    ) -> None:
        if action.source is None:
            raise ValueError(
                "CREATE_SOURCE requires source"
            )

        source_orm = self._asset_source_to_orm(
            action.source
        )

        session.add(source_orm)

    def _execute_update_source(
        self,
        session: Session,
        action: Action,
    ) -> None:
        if action.source is None:
            raise ValueError(
                "UPDATE_SOURCE requires source"
            )

        source = action.source

        source_orm = session.get(
            AssetSourceORM,
            UUID(source.id),
        )

        if source_orm is None:
            raise ValueError(
                f"Source not found: {source.id}"
            )

        if source.blob_id is None:
            raise ValueError(
                "UPDATE_SOURCE requires blob_id"
            )

        source_orm.blob_id = UUID(source.blob_id)
        source_orm.path = source.path
        source_orm.name = source.name
        source_orm.version_tag = source.version_tag
        source_orm.metadata_ = source.metadata

    def _execute_deactivate_source(
        self,
        session: Session,
        action: Action,
    ) -> None:
        if action.source is None:
            raise ValueError(
                "DEACTIVATE_SOURCE requires source"
            )

        source = action.source

        source_orm = session.get(
            AssetSourceORM,
            UUID(source.id),
        )

        if source_orm is None:
            raise ValueError(
                f"Source not found: {source.id}"
            )

        source_orm.is_active = source.is_active
        source_orm.deleted_at = source.deleted_at
