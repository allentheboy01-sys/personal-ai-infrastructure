from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseModel):
    """PostgreSQL 连接配置。"""

    url: str


class NextcloudSettings(BaseModel):
    """Nextcloud Provider 连接配置。"""

    url: str
    user: str
    password: str


class Settings(BaseSettings):
    """PDI 应用启动所需的统一配置。"""

    database: DatabaseSettings
    nextcloud: NextcloudSettings

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )