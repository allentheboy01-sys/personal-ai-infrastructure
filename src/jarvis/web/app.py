import json
import mimetypes
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import Engine

from jarvis.runtime import ActiveTurnRegistry, RuntimeAdapter, RuntimeEvent
from jarvis.pdi_client import PDIClient, PDIClientError, PDIProviderNotFound, PDIResourceNotFound, RepresentationError, ResourceAccessClient, UnavailablePDIClient
from jarvis.state import ActiveTurnError, JarvisStateStore, NotFoundError
from jarvis.state.database import create_session_factory

from .auth import AuthAdapter
from .coordinator import TurnCoordinator
from .schemas import ConversationDetailResponse, ConversationSummaryResponse, CreateConversationRequest, CreateTurnRequest, MessageResponse, ProviderDetailResponse, ProviderSummaryResponse, ResourceDetailResponse, ResourcePageResponse, ResourceRefResponse, ResourceSummaryResponse, TurnCreatedResponse, TurnResponse
from .security import BrowserSecurityMiddleware


@dataclass(frozen=True, slots=True)
class JarvisWebSettings:
    allowed_origin: str
    static_dir: Path


def create_app(*, engine: Engine, settings: JarvisWebSettings, auth_adapter: AuthAdapter, runtime: RuntimeAdapter, pdi_client: PDIClient | None = None, resource_access: ResourceAccessClient | None = None) -> FastAPI:
    state = JarvisStateStore(create_session_factory(engine))
    registry = ActiveTurnRegistry()
    coordinator = TurnCoordinator(state, runtime, registry)
    product_client = pdi_client or UnavailablePDIClient()
    representations = resource_access or ResourceAccessClient(None)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        state.interrupt_orphaned_running_turns()
        try:
            await product_client.start()
        except PDIClientError:
            pass
        try:
            yield
        finally:
            await product_client.close()

    app = FastAPI(title="Jarvis Web", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(BrowserSecurityMiddleware, auth_adapter=auth_adapter, allowed_origin=settings.allowed_origin)
    app.state.jarvis_state = state
    app.state.active_turns = registry
    router = APIRouter(prefix="/api/v1")

    @router.get("/conversations", response_model=list[ConversationSummaryResponse])
    async def list_conversations() -> list[ConversationSummaryResponse]:
        return [ConversationSummaryResponse.model_validate(item) for item in state.list_conversations()]

    @router.post("/conversations", response_model=ConversationSummaryResponse, status_code=201)
    async def create_conversation(payload: CreateConversationRequest) -> ConversationSummaryResponse:
        return ConversationSummaryResponse.model_validate(state.create_conversation(payload.title))

    @router.get("/conversations/{conversation_id}", response_model=ConversationDetailResponse)
    async def get_conversation(conversation_id: UUID) -> ConversationDetailResponse:
        try:
            item = state.get_conversation(conversation_id)
        except NotFoundError as error:
            raise HTTPException(404, str(error)) from error
        messages = []
        for message in item.messages:
            refs = [ResourceRefResponse(resource_ref=ref.resource_ref, ordinal=ref.ordinal) for ref in message.resource_refs]
            hydrated = []
            if refs:
                try:
                    hydrated = [_resource_summary(resource) for resource in await product_client.hydrate_resources([ref.resource_ref for ref in refs])]
                except PDIClientError:
                    hydrated = []
            messages.append(MessageResponse(id=message.id, role=message.role, body=message.body, created_at=message.created_at, resource_refs=refs, resources=hydrated))
        return ConversationDetailResponse(id=item.id, title=item.title, created_at=item.created_at, updated_at=item.updated_at, archived_at=item.archived_at, messages=messages)

    @router.post("/conversations/{conversation_id}/turns", response_model=TurnCreatedResponse, status_code=201)
    async def create_turn(conversation_id: UUID, payload: CreateTurnRequest) -> TurnCreatedResponse:
        try:
            turn_id = await coordinator.start(conversation_id, payload.body)
        except NotFoundError as error:
            raise HTTPException(404, str(error)) from error
        except ActiveTurnError as error:
            raise HTTPException(409, str(error)) from error
        return TurnCreatedResponse(turn_id=turn_id)

    @router.get("/turns/{turn_id}", response_model=TurnResponse)
    async def get_turn(turn_id: UUID) -> TurnResponse:
        try:
            turn = state.get_turn(turn_id)
        except NotFoundError as error:
            raise HTTPException(404, str(error)) from error
        snapshot = registry.snapshot(turn_id)
        return TurnResponse(id=turn.id, conversation_id=turn.conversation_id, user_message_id=turn.user_message_id, assistant_message_id=turn.assistant_message_id, status=turn.status, started_at=turn.started_at, completed_at=turn.completed_at, error_code=turn.error_code, sequence=snapshot.sequence if snapshot else None, phase=snapshot.phase if snapshot else None, provisional_text=snapshot.provisional_text if snapshot and turn.status == "running" else None)

    @router.get("/turns/{turn_id}/events")
    async def stream_events(turn_id: UUID, request: Request) -> StreamingResponse:
        try:
            state.get_turn(turn_id)
        except NotFoundError as error:
            raise HTTPException(404, str(error)) from error
        if not registry.contains(turn_id):
            raise HTTPException(409, "event_stream_unavailable")
        raw_last = request.headers.get("Last-Event-ID", "0")
        try:
            after = max(0, int(raw_last))
        except ValueError as error:
            raise HTTPException(400, "invalid_last_event_id") from error

        async def events() -> AsyncIterator[str]:
            async for event in registry.stream(turn_id, after):
                yield _sse(event)

        return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "private, no-store", "X-Accel-Buffering": "no"})

    @router.post("/turns/{turn_id}/cancel", response_model=TurnResponse)
    async def cancel_turn(turn_id: UUID) -> TurnResponse:
        try:
            await coordinator.cancel(turn_id)
            turn = state.get_turn(turn_id)
        except NotFoundError as error:
            raise HTTPException(404, str(error)) from error
        return TurnResponse(id=turn.id, conversation_id=turn.conversation_id, user_message_id=turn.user_message_id, assistant_message_id=turn.assistant_message_id, status=turn.status, started_at=turn.started_at, completed_at=turn.completed_at, error_code=turn.error_code)

    @router.get("/resources", response_model=ResourcePageResponse)
    async def list_resources(query: str | None = None, provider: str | None = None, resource_type: str | None = None, limit: int = 24, cursor: str | None = None) -> ResourcePageResponse:
        if resource_type is not None and resource_type not in {"file", "message"}:
            raise HTTPException(400, "invalid_resource_type")
        if provider is not None and provider not in {"gmail", "immich", "nextcloud"}:
            raise HTTPException(400, "invalid_provider")
        try:
            page = await product_client.list_resources(query=query, provider=provider, resource_type=resource_type, limit=min(max(limit, 1), 50), cursor=cursor)
        except PDIClientError as error:
            raise _pdi_http_error(error) from error
        return ResourcePageResponse(resources=[_resource_summary(item) for item in page.resources], next_cursor=page.next_cursor)

    @router.get("/resources/{resource_ref}", response_model=ResourceDetailResponse)
    async def get_resource(resource_ref: str) -> ResourceDetailResponse:
        try:
            detail = await product_client.get_resource(resource_ref)
        except PDIClientError as error:
            raise _pdi_http_error(error) from error
        return ResourceDetailResponse(summary=_resource_summary(detail.summary), facts=list(detail.facts), mime_type=detail.mime_type, size_bytes=detail.size_bytes, notice=detail.notice)

    @router.get("/resources/{resource_ref}/representation")
    async def get_representation(resource_ref: str, kind: str = "thumbnail") -> StreamingResponse:
        try:
            context = representations.stream(resource_ref, kind)
            stream = await context.__aenter__()
        except RepresentationError as error:
            raise HTTPException(error.status_code, error.code) from error

        async def body() -> AsyncIterator[bytes]:
            try:
                async for chunk in stream.body:
                    yield chunk
            finally:
                await context.__aexit__(None, None, None)
        headers = {"Cache-Control": "private, no-store"}
        if stream.content_length is not None:
            headers["Content-Length"] = str(stream.content_length)
        return StreamingResponse(body(), media_type=stream.content_type, headers=headers)

    @router.get("/providers", response_model=list[ProviderSummaryResponse])
    async def list_providers() -> list[ProviderSummaryResponse]:
        try:
            return [_provider_summary(item) for item in await product_client.list_providers()]
        except PDIClientError as error:
            raise _pdi_http_error(error) from error

    @router.get("/providers/{provider_ref}", response_model=ProviderDetailResponse)
    async def get_provider(provider_ref: str) -> ProviderDetailResponse:
        try:
            detail = await product_client.get_provider(provider_ref)
        except PDIClientError as error:
            raise _pdi_http_error(error) from error
        return ProviderDetailResponse(summary=_provider_summary(detail.summary), description=detail.description, capabilities=list(detail.capabilities), stages=list(detail.stages))

    app.include_router(router)

    @app.get("/{client_path:path}")
    async def static_files(client_path: str) -> Response:
        if client_path.startswith("api/"):
            raise HTTPException(404, "api_not_found")
        root = settings.static_dir.resolve()
        requested = (root / client_path).resolve()
        if client_path and requested.is_relative_to(root) and requested.is_file():
            media_type = mimetypes.guess_type(requested.name)[0] or "application/octet-stream"
            return Response(requested.read_bytes(), media_type=media_type)
        index = root / "index.html"
        if not index.is_file():
            raise HTTPException(503, "frontend_build_unavailable")
        return Response(index.read_bytes(), media_type="text/html")

    return app


def _sse(event: RuntimeEvent) -> str:
    payload = {"turn_id": str(event.turn_id), "sequence": event.sequence, "type": event.type.value}
    if event.phase is not None:
        payload["phase"] = event.phase.value
    if event.delta is not None:
        payload["delta"] = event.delta
    if event.error_code is not None:
        payload["error_code"] = event.error_code
    return f"id: {event.sequence}\nevent: {event.type.value}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"


def _resource_summary(item) -> ResourceSummaryResponse:
    return ResourceSummaryResponse(resource_ref=item.resource_ref, resource_type=item.resource_type, title=item.title, secondary_text=item.secondary_text, timestamp=item.timestamp, presentation_kind=item.presentation_kind, presentation_label=item.presentation_label, providers=list(item.providers), capabilities={"detail": item.capabilities.detail, "preview": item.capabilities.preview, "open": item.capabilities.open})


def _provider_summary(item) -> ProviderSummaryResponse:
    return ProviderSummaryResponse(provider_ref=item.provider_ref, provider_type=item.provider_type, display_name=item.display_name, category=item.category, configured=item.configured, access_mode=item.access_mode, resource_count=item.resource_count, operational_state=item.operational_state, last_success_at=item.last_success_at)


def _pdi_http_error(error: PDIClientError) -> HTTPException:
    if isinstance(error, (PDIResourceNotFound, PDIProviderNotFound)):
        return HTTPException(404, error.code)
    return HTTPException(503 if error.code == "pdi_unavailable" else 502, error.code)
