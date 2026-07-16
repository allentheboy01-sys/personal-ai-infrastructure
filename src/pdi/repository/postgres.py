from uuid import UUID

from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from pdi.decision import Action, ActionType, Decision
from pdi.models import Asset, AssetSource, Blob
from pdi.repository.base import Repository

from pdi.repository.orm.asset import AssetORM
from pdi.repository.orm.blob import BlobORM
from pdi.repository.orm.asset_source import AssetSourceORM

class PostgreSQLRepository(Repository):
    def __init__(self, engine: Engine) -> None:
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
    def _asset_to_orm(asset: Asset) -> AssetORM:
        return AssetORM(
            id=UUID(asset.id),
            title=asset.title,
            metadata_=asset.metadata,
            created_at=asset.created_at,
            updated_at=asset.updated_at,
        )

    @staticmethod
    def _asset_to_domain(asset_orm: AssetORM) -> Asset:
        return Asset(
            id=str(asset_orm.id),
            title=asset_orm.title,
            metadata=dict(asset_orm.metadata_),
            created_at=asset_orm.created_at,
            updated_at=asset_orm.updated_at,
        )
    
    @staticmethod
    def _blob_to_orm(blob: Blob) -> BlobORM:
        return BlobORM(
            id=UUID(blob.id),
            asset_id=UUID(blob.asset_id),
            hash=blob.hash,
            size=blob.size,
            mime_type=blob.mime_type,
        )

    @staticmethod
    def _blob_to_domain(blob_orm: BlobORM) -> Blob:
        return Blob(
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
        return AssetSourceORM(
            id=UUID(source.id),
            blob_id=UUID(source.blob_id),
            provider=source.provider,
            external_id=source.external_id,
            path=source.path,
            name=source.name,
            version_tag=source.version_tag,
            metadata_=source.metadata,
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

                        case _:
                            raise ValueError(
                                f"Unsupported action type: {action.type}"
                            )

                    # 把当前 Action 的变化写入数据库，
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

        assert action.asset is not None, "Asset must be provided for CREATE_ASSET action."
        asset_orm = self._asset_to_orm(action.asset)

        session.add(asset_orm)

    def _execute_create_blob(
        self,
        session: Session,
        action: Action,
    ) -> None:
        assert action.blob is not None, "Blob must be provided for CREATE_BLOB action."
        blob_orm = self._blob_to_orm(action.blob)

        session.add(blob_orm)

    def _execute_create_source(
        self,
        session: Session,
        action: Action,
    ) -> None:
        assert action.source is not None, "Source must be provided for CREATE_SOURCE action."
        source_orm = self._asset_source_to_orm(action.source)

        session.add(source_orm)

    def _execute_update_source(
        self,
        session: Session,
        action: Action,
    ) -> None:
        assert action.source is not None, "Source must be provided for UPDATE_SOURCE action."
        raise NotImplementedError