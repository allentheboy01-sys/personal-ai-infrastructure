from sqlalchemy import Engine, create_engine



def create_postgres_engine(database_url: str) -> Engine:
    """根据数据库连接地址创建 PDI 使用的 SQLAlchemy Engine。"""

    return create_engine(
        database_url,
        pool_pre_ping=True,
    )
