from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CreateConversationRequest(BaseModel):
    title: str = Field(default="New conversation", max_length=200)


class CreateTurnRequest(BaseModel):
    body: str = Field(min_length=1, max_length=100_000)

    @field_validator("body")
    @classmethod
    def body_must_have_visible_content(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("message body must not be empty")
        return clean


class ResourceRefResponse(BaseModel):
    resource_ref: str
    ordinal: int


class ResourceCapabilitiesResponse(BaseModel):
    detail: bool
    preview: bool
    open: bool
    playback: bool


class ResourceSummaryResponse(BaseModel):
    resource_ref: str
    resource_type: str
    title: str
    secondary_text: str | None
    timestamp: str | None
    presentation_kind: str
    presentation_label: str
    providers: list[str]
    capabilities: ResourceCapabilitiesResponse


class ResourceDetailResponse(BaseModel):
    summary: ResourceSummaryResponse
    facts: list[tuple[str, str]]
    mime_type: str | None
    size_bytes: int | None
    notice: str | None


class ResourcePageResponse(BaseModel):
    resources: list[ResourceSummaryResponse]
    next_cursor: str | None


class ProviderSummaryResponse(BaseModel):
    provider_ref: str
    provider_type: str
    display_name: str
    category: str
    configured: bool
    access_mode: str
    resource_count: int
    operational_state: str
    last_success_at: str | None


class ProviderDetailResponse(BaseModel):
    summary: ProviderSummaryResponse
    description: str
    capabilities: list[str]
    stages: list[tuple[str, str]]


class MessageResponse(BaseModel):
    id: UUID
    role: str
    body: str
    created_at: datetime
    resource_refs: list[ResourceRefResponse] = Field(default_factory=list)
    resources: list[ResourceSummaryResponse] = Field(default_factory=list)


class ConversationSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class ConversationDetailResponse(ConversationSummaryResponse):
    messages: list[MessageResponse]


class TurnCreatedResponse(BaseModel):
    turn_id: UUID


class TurnResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    user_message_id: UUID
    assistant_message_id: UUID | None
    status: str
    started_at: datetime
    completed_at: datetime | None
    error_code: str | None
    sequence: int | None = None
    phase: str | None = None
    provisional_text: str | None = None
