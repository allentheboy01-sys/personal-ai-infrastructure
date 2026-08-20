"""Fail-closed production composition for the Jarvis Web process.

The browser never participates in this selection.  Deployment configuration
constructs every external boundary before the FastAPI application is created.
"""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from jarvis.pdi_client.mcp import MCPClientConfig, MCPPDIClient
from jarvis.pdi_client.resource_access import ResourceAccessClient
from jarvis.runtime.hermes_adapter import HermesBridgeConfig, HermesRuntimeAdapter
from jarvis.state.database import create_jarvis_engine

from .app import JarvisWebSettings, create_app
from .auth import TailscaleServeAuth


PositiveFloat = Annotated[float, Field(gt=0)]
PositiveInt = Annotated[int, Field(gt=0)]


class ProductionSettings(BaseSettings):
    """Validated, deployment-owned settings for exactly one production worker."""

    model_config = SettingsConfigDict(env_prefix="JARVIS_", extra="forbid")

    database_url: SecretStr
    allowed_tailscale_login: SecretStr
    allowed_origin: str
    static_dir: Path
    hermes_bridge_command: str
    pdi_mcp_command: str
    resource_access_socket: Path
    bind_host: str = "127.0.0.1"
    bind_port: Annotated[int, Field(ge=1, le=65535)] = 8765
    runtime_timeout_seconds: PositiveFloat = 600.0
    runtime_interrupt_grace_seconds: Annotated[float, Field(ge=0)] = 2.0
    runtime_terminate_grace_seconds: Annotated[float, Field(ge=0)] = 2.0
    runtime_max_request_bytes: PositiveInt = 1_048_576
    runtime_max_line_bytes: PositiveInt = 262_144
    runtime_max_stderr_bytes: PositiveInt = 65_536
    runtime_max_visible_bytes: PositiveInt = 4_194_304
    pdi_timeout_seconds: PositiveFloat = 20.0
    pdi_max_hydration_refs: Annotated[int, Field(ge=1, le=8)] = 8
    resource_access_timeout_seconds: PositiveFloat = 20.0

    @field_validator("allowed_origin")
    @classmethod
    def validate_origin(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.netloc or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ValueError("allowed origin must be an exact HTTPS origin")
        return value.rstrip("/")

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if not raw.startswith(("postgresql://", "postgresql+psycopg://")):
            raise ValueError("production Jarvis state requires PostgreSQL")
        return value

    @field_validator("hermes_bridge_command", "pdi_mcp_command")
    @classmethod
    def validate_command(cls, value: str) -> str:
        parts = shlex.split(value)
        if not parts or not Path(parts[0]).is_absolute():
            raise ValueError("production commands must start with an absolute executable path")
        return value

    @field_validator("bind_host")
    @classmethod
    def validate_bind_host(cls, value: str) -> str:
        if value != "127.0.0.1":
            raise ValueError("production listener must use IPv4 loopback")
        return value

    @property
    def hermes_command(self) -> tuple[str, ...]:
        return tuple(shlex.split(self.hermes_bridge_command))

    @property
    def pdi_command(self) -> tuple[str, ...]:
        return tuple(shlex.split(self.pdi_mcp_command))


def create_production_app(settings: ProductionSettings | None = None):
    """Build the production graph; no mock or unavailable fallback is possible."""

    config = settings or ProductionSettings()  # type: ignore[call-arg]
    if not config.static_dir.joinpath("index.html").is_file():
        raise ValueError("JARVIS_STATIC_DIR must contain the production index.html")

    pdi_command, *pdi_args = config.pdi_command
    engine = create_jarvis_engine(config.database_url.get_secret_value())
    runtime = HermesRuntimeAdapter(
        HermesBridgeConfig(
            command=config.hermes_command,
            timeout_seconds=config.runtime_timeout_seconds,
            interrupt_grace_seconds=config.runtime_interrupt_grace_seconds,
            terminate_grace_seconds=config.runtime_terminate_grace_seconds,
            max_request_bytes=config.runtime_max_request_bytes,
            max_line_bytes=config.runtime_max_line_bytes,
            max_stderr_bytes=config.runtime_max_stderr_bytes,
            max_visible_bytes=config.runtime_max_visible_bytes,
        )
    )
    pdi_client = MCPPDIClient(
        MCPClientConfig(
            command=pdi_command,
            args=tuple(pdi_args),
            env={},
            timeout_seconds=config.pdi_timeout_seconds,
            max_hydration_refs=config.pdi_max_hydration_refs,
        )
    )
    resource_access = ResourceAccessClient(
        str(config.resource_access_socket),
        timeout_seconds=config.resource_access_timeout_seconds,
    )
    return create_app(
        engine=engine,
        settings=JarvisWebSettings(config.allowed_origin, config.static_dir),
        auth_adapter=TailscaleServeAuth(frozenset({config.allowed_tailscale_login.get_secret_value()})),
        runtime=runtime,
        pdi_client=pdi_client,
        resource_access=resource_access,
    )
