from pydantic import BaseModel, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseModel):
    """PostgreSQL 连接配置。"""

    url: str


class NextcloudSettings(BaseModel):
    """Nextcloud Provider 连接配置。"""

    url: str
    user: str
    password: str


class ImmichSettings(BaseModel):
    """Immich Provider 连接配置。"""

    url: str
    api_key: str


class GmailSettings(BaseModel):
    """Gmail read-only runtime configuration."""

    token_file: str = "/etc/pdi/gmail-oauth-token.json"


class LoggingSettings(BaseModel):
    """PDI 日志配置。"""

    level: str = "INFO"


class Settings(BaseSettings):
    """PDI 应用启动所需的统一配置。"""

    database: DatabaseSettings
    nextcloud: NextcloudSettings | None = None
    immich: ImmichSettings | None = None
    gmail: GmailSettings = Field(default_factory=GmailSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )


class PDIConfigurationError(RuntimeError):
    """Sanitized application-composition configuration failure."""


class _CoreSettings(BaseSettings):
    """Persistence and provider-neutral application configuration."""

    database: DatabaseSettings
    gmail: GmailSettings = Field(default_factory=GmailSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )


def _configuration_error(error: ValidationError) -> PDIConfigurationError:
    locations = {item["loc"][0] for item in error.errors() if item["loc"]}
    if "database" in locations:
        message = "DATABASE__URL is required for PDI persistence"
    elif "nextcloud" in locations:
        message = (
            "Nextcloud configuration is incomplete; set NEXTCLOUD__URL, "
            "NEXTCLOUD__USER, and NEXTCLOUD__PASSWORD"
        )
    elif "immich" in locations:
        message = (
            "Immich configuration is incomplete; set IMMICH__URL and "
            "IMMICH__API_KEY"
        )
    else:
        message = "PDI configuration is invalid"
    return PDIConfigurationError(message)


def load_settings(selected_provider: str | None = None) -> Settings:
    """Load only the configuration relevant to the selected sync mode."""

    try:
        if selected_provider is None:
            return Settings()
        core = _CoreSettings()
    except ValidationError as error:
        raise _configuration_error(error) from None

    nextcloud = None
    immich = None
    if selected_provider == "nextcloud":
        nextcloud = load_nextcloud_settings()
    elif selected_provider == "immich":
        immich = load_immich_settings()

    return Settings(
        database=core.database,
        nextcloud=nextcloud,
        immich=immich,
        gmail=core.gmail,
        logging=core.logging,
        _env_file=None,
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


class _ImmichOnlySettings(BaseSettings):
    """Immich enrichment commands' minimum Provider configuration."""

    immich: ImmichSettings

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )


class _NextcloudOnlySettings(BaseSettings):
    """Nextcloud enrichment commands' minimum Provider configuration."""

    nextcloud: NextcloudSettings

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
        raise PDIConfigurationError(
            "DATABASE__URL is required for database operations"
        ) from None


def load_immich_settings() -> ImmichSettings:
    """Read only the Immich settings required by enrichment."""

    try:
        return _ImmichOnlySettings().immich
    except ValidationError:
        raise PDIConfigurationError(
            "IMMICH__URL and IMMICH__API_KEY are required for "
            "Immich operations"
        ) from None


def load_nextcloud_settings() -> NextcloudSettings:
    """Read only the Nextcloud settings required by enrichment."""

    try:
        return _NextcloudOnlySettings().nextcloud
    except ValidationError:
        raise PDIConfigurationError(
            "NEXTCLOUD__URL, NEXTCLOUD__USER, and "
            "NEXTCLOUD__PASSWORD are required for Nextcloud operations"
        ) from None
