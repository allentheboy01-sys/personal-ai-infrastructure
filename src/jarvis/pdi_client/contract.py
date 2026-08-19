from __future__ import annotations

from typing import Protocol

from .models import ProviderDetail, ProviderSummary, ResourceDetail, ResourcePage, ResourceSummary


class PDIClientError(RuntimeError):
    code = "pdi_unavailable"


class PDIUnavailableError(PDIClientError):
    pass


class PDIContractError(PDIClientError):
    code = "pdi_invalid_response"


class PDIResourceNotFound(PDIClientError):
    code = "resource_not_found"


class PDIProviderNotFound(PDIClientError):
    code = "provider_not_found"


class PDIClient(Protocol):
    async def start(self) -> None: ...
    async def close(self) -> None: ...
    async def list_resources(self, *, query: str | None = None, provider: str | None = None, resource_type: str | None = None, limit: int = 24, cursor: str | None = None) -> ResourcePage: ...
    async def get_resource(self, resource_ref: str) -> ResourceDetail: ...
    async def hydrate_resources(self, resource_refs: list[str]) -> tuple[ResourceSummary, ...]: ...
    async def list_providers(self) -> tuple[ProviderSummary, ...]: ...
    async def get_provider(self, provider_ref: str) -> ProviderDetail: ...


class UnavailablePDIClient:
    async def start(self) -> None: return None
    async def close(self) -> None: return None
    async def _fail(self): raise PDIUnavailableError("pdi_unavailable")
    async def list_resources(self, **_kwargs): return await self._fail()
    async def get_resource(self, _resource_ref: str): return await self._fail()
    async def hydrate_resources(self, _resource_refs: list[str]): return await self._fail()
    async def list_providers(self): return await self._fail()
    async def get_provider(self, _provider_ref: str): return await self._fail()
