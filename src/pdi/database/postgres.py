import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _PROJECT_ROOT / ".env"


def create_postgres_engine() -> Engine:
    """
    创建 PDI 使用的 SQLAlchemy Engine。

    DATABASE_URL 从项目根目录下的 .env 文件读取。
    """
    load_dotenv(_ENV_PATH)

    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        raise RuntimeError(
            f"DATABASE_URL is not configured in {_ENV_PATH}"
        )

    return create_engine(
        database_url,
        pool_pre_ping=True,
    )
