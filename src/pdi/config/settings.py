from pydantic import BaseModel, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseModel):
    """PostgreSQL 连接配置。"""

    url: str


class NextcloudSettings(BaseModel):
    """Nextcloud Provider 连接配置。"""

    url: str
    user: str
    password: str

class LoggingSettings(BaseModel):
    """PDI 日志配置。"""

    level: str = "INFO"

class Settings(BaseSettings):
    """PDI 应用启动所需的统一配置。"""

    database: DatabaseSettings
    nextcloud: NextcloudSettings
    logging: LoggingSettings = LoggingSettings()

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )


class _DatabaseOnlySettings(BaseSettings):
    """数据库运维命令所需的最小配置。"""

    database: DatabaseSettings

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )


def load_database_url() -> str:
    """读取数据库 URL，不要求 Provider 配置。"""

    try:
        return _DatabaseOnlySettings().database.url
    except ValidationError:
        raise RuntimeError(
            "DATABASE__URL is required for database operations"
        ) from None
