from __future__ import annotations

import asyncio
import os
from contextlib import AsyncExitStack
from dataclasses import dataclass

from mcp import ClientSession, StdioServerParameters, stdio_client

from .contract import PDIContractError, PDIProviderNotFound, PDIResourceNotFound, PDIUnavailableError
from .models import ProviderDetail, ProviderSummary, ResourceDetail, ResourcePage, ResourceSummary
from .projection import provider_detail, project_providers, project_resource_detail, project_resource_page

REQUIRED_TOOLS = frozenset({"pdi_list_recent_resources", "pdi_search_resources", "pdi_aggregate_resources", "pdi_retrieve_resources", "pdi_rich_retrieve_resources", "pdi_get_resource", "pdi_get_resource_observations", "pdi_get_data_status"})


@dataclass(frozen=True, slots=True)
class MCPClientConfig:
    command: str
    args: tuple[str, ...] = ()
    env: dict[str, str] | None = None
    cwd: str | None = None
    timeout_seconds: float = 20.0
    max_hydration_refs: int = 8


class MCPPDIClient:
    def __init__(self, config: MCPClientConfig) -> None:
        self._config = config
        self._lock = asyncio.Lock()
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    async def start(self) -> None:
        async with self._lock:
            if self._session is None:
                try:
                    await self._connect()
                except PDIContractError:
                    raise
                except Exception as error:
                    raise PDIUnavailableError("pdi_unavailable") from error

    async def close(self) -> None:
        async with self._lock:
            await self._disconnect()

    async def _connect(self) -> None:
        stack = AsyncExitStack()
        try:
            params = StdioServerParameters(command=self._config.command, args=list(self._config.args), env=self._config.env or {}, cwd=self._config.cwd)
            # Child diagnostics are intentionally discarded: raw launcher/MCP stderr
            # is neither a product response nor safe application-log material.
            errlog = stack.enter_context(open(os.devnull, "w", encoding="utf-8"))
            streams = await stack.enter_async_context(stdio_client(params, errlog=errlog))
            session = await stack.enter_async_context(ClientSession(streams[0], streams[1], read_timeout_seconds=self._config.timeout_seconds))
            await session.initialize()
            listing = await session.list_tools()
            names = {tool.name for tool in listing.tools}
            if names != REQUIRED_TOOLS:
                raise PDIContractError("pdi_tool_contract_mismatch")
        except Exception:
            await stack.aclose()
            raise
        self._stack, self._session = stack, session

    async def _disconnect(self) -> None:
        stack, self._stack, self._session = self._stack, None, None
        if stack is not None:
            await stack.aclose()

    async def _call(self, tool: str, arguments: dict[str, object]) -> object:
        async with self._lock:
            for attempt in range(2):
                try:
                    if self._session is None:
                        await self._connect()
                    assert self._session is not None
                    result = await self._session.call_tool(tool, arguments)
                    if result.is_error or not isinstance(result.structured_content, dict):
                        raise PDIContractError("pdi_invalid_response")
                    return result.structured_content
                except PDIContractError:
                    raise
                except Exception as error:
                    await self._disconnect()
                    if attempt:
                        raise PDIUnavailableError("pdi_unavailable") from error
            raise PDIUnavailableError("pdi_unavailable")

    async def list_resources(self, *, query: str | None = None, provider: str | None = None, resource_type: str | None = None, limit: int = 24, cursor: str | None = None) -> ResourcePage:
        arguments: dict[str, object] = {"limit": min(max(limit, 1), 50)}
        for key, value in (("provider", provider), ("resource_type", resource_type), ("cursor", cursor)):
            if value is not None: arguments[key] = value
        tool = "pdi_search_resources" if query else "pdi_list_recent_resources"
        if query: arguments["query"] = query
        return project_resource_page(await self._call(tool, arguments))

    async def get_resource(self, resource_ref: str) -> ResourceDetail:
        try:
            return project_resource_detail(await self._call("pdi_get_resource", {"resource_ref": resource_ref}))
        except PDIResourceNotFound:
            raise

    async def hydrate_resources(self, resource_refs: list[str]) -> tuple[ResourceSummary, ...]:
        refs = list(dict.fromkeys(resource_refs))[: self._config.max_hydration_refs]
        hydrated: list[ResourceSummary] = []
        for ref in refs:
            try:
                hydrated.append((await self.get_resource(ref)).summary)
            except PDIResourceNotFound:
                continue
        return tuple(hydrated)

    async def list_providers(self) -> tuple[ProviderSummary, ...]:
        aggregate = await self._call("pdi_aggregate_resources", {"group_by": "provider"})
        status = await self._call("pdi_get_data_status", {})
        return project_providers(aggregate, status)

    async def get_provider(self, provider_ref: str) -> ProviderDetail:
        if provider_ref not in {"gmail", "immich", "nextcloud"}:
            raise PDIProviderNotFound("provider_not_found")
        summary = next(item for item in await self.list_providers() if item.provider_ref == provider_ref)
        return provider_detail(summary)
