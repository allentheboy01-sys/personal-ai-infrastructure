import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import Engine

from jarvis.runtime import ActiveTurnRegistry, RuntimeAdapter, RuntimeEvent
from jarvis.state import ActiveTurnError, JarvisStateStore, NotFoundError
from jarvis.state.database import create_session_factory

from .auth import AuthAdapter
from .coordinator import TurnCoordinator
from .schemas import ConversationDetailResponse, ConversationSummaryResponse, CreateConversationRequest, CreateTurnRequest, MessageResponse, ResourceRefResponse, TurnCreatedResponse, TurnResponse
from .security import BrowserSecurityMiddleware


@dataclass(frozen=True, slots=True)
class JarvisWebSettings:
    allowed_origin: str
    static_dir: Path


def create_app(*, engine: Engine, settings: JarvisWebSettings, auth_adapter: AuthAdapter, runtime: RuntimeAdapter) -> FastAPI:
    state = JarvisStateStore(create_session_factory(engine))
    registry = ActiveTurnRegistry()
    coordinator = TurnCoordinator(state, runtime, registry)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        state.interrupt_orphaned_running_turns()
        yield

    app = FastAPI(title="Jarvis Web", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(BrowserSecurityMiddleware, auth_adapter=auth_adapter, allowed_origin=settings.allowed_origin)
    app.state.jarvis_state = state
    app.state.active_turns = registry
    router = APIRouter(prefix="/api/v1")

    @router.get("/conversations", response_model=list[ConversationSummaryResponse])
    def list_conversations() -> list[ConversationSummaryResponse]:
        return [ConversationSummaryResponse.model_validate(item) for item in state.list_conversations()]

    @router.post("/conversations", response_model=ConversationSummaryResponse, status_code=201)
    def create_conversation(payload: CreateConversationRequest) -> ConversationSummaryResponse:
        return ConversationSummaryResponse.model_validate(state.create_conversation(payload.title))

    @router.get("/conversations/{conversation_id}", response_model=ConversationDetailResponse)
    def get_conversation(conversation_id: UUID) -> ConversationDetailResponse:
        try:
            item = state.get_conversation(conversation_id)
        except NotFoundError as error:
            raise HTTPException(404, str(error)) from error
        messages = [MessageResponse(id=message.id, role=message.role, body=message.body, created_at=message.created_at, resource_refs=[ResourceRefResponse(resource_ref=ref.resource_ref, ordinal=ref.ordinal) for ref in message.resource_refs]) for message in item.messages]
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
    def get_turn(turn_id: UUID) -> TurnResponse:
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

    app.include_router(router)

    @app.get("/{client_path:path}")
    async def static_files(client_path: str) -> FileResponse:
        if client_path.startswith("api/"):
            raise HTTPException(404, "api_not_found")
        root = settings.static_dir.resolve()
        requested = (root / client_path).resolve()
        if client_path and requested.is_relative_to(root) and requested.is_file():
            return FileResponse(requested)
        index = root / "index.html"
        if not index.is_file():
            raise HTTPException(503, "frontend_build_unavailable")
        return FileResponse(index)

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
