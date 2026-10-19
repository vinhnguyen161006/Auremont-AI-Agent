from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from backend.core.enums import LeadPurpose, LeadTier, LeadUrgency, SessionStatus
from backend.schemas.chat import ChatText, MessageResponse
from backend.utils.phone import normalise_vn_mobile


class CustomerRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str | None = Field(default=None, max_length=255)
    phone: str | None = None
    session_id: int | None = None
    visitor_token: str | None = None

    @field_validator("phone", mode="before")
    @classmethod
    def _normalise_phone(cls, value: object) -> object:
        return normalise_vn_mobile(value) if isinstance(value, str) else value

    @field_validator("full_name", mode="before")
    @classmethod
    def _strip_full_name(cls, value: object) -> object:
        return value.strip() or None if isinstance(value, str) else value


class AnonymousSessionResponse(BaseModel):
    session_id: int
    visitor_token: str


class AnonymousSessionClaimRequest(BaseModel):
    session_id: int
    visitor_token: str


class CustomerChatSessionCreate(BaseModel):
    title: str | None = None
    project_id: str | None = None


class CustomerChatSessionResponse(BaseModel):
    id: int
    customer_id: int | None = None
    title: str | None = None
    project_id: str | None = None
    status: SessionStatus
    created_at: datetime

    model_config = {"from_attributes": True}


class CustomerAskRequest(BaseModel):
    content: ChatText


class CustomerAskResponse(MessageResponse):
    gate: Literal["turn_limit", "daily_limit", "closing_intent", "human_request"] | None = None
    status: SessionStatus = SessionStatus.BOT_HANDLING


class CustomerNeeds(BaseModel):
    purchase_purpose: str | None = None
    projects: list[str] = Field(default_factory=list)
    property_types: list[str] = Field(default_factory=list)
    unit_types: list[str] = Field(default_factory=list)
    budget_min: int | None = Field(default=None, ge=0, description="Ngân sách tối thiểu bằng VND")
    budget_max: int | None = Field(default=None, ge=0, description="Ngân sách tối đa bằng VND")
    area_min_m2: float | None = Field(default=None, ge=0)
    area_max_m2: float | None = Field(default=None, ge=0)
    preferred_floor: str | None = None
    preferred_view: str | None = None
    purchase_timeline: str | None = None

    @field_validator("projects", "property_types", "unit_types", mode="after")
    @classmethod
    def _limit_multi_value_needs(cls, values: list[str]) -> list[str]:
        return values[:10]


class ConsideredUnit(BaseModel):
    unit_code: str
    project_id: str | None = None
    customer_reaction: str | None = None
    last_mentioned_at: datetime | None = None
    inventory_recheck_required: bool = True
    evidence_message_ids: list[int] = Field(default_factory=list)

    @field_validator("evidence_message_ids", mode="after")
    @classmethod
    def _limit_evidence_message_ids(cls, values: list[int]) -> list[int]:
        return values[:10]


class SaleCommitment(BaseModel):
    content: str
    status: Literal["pending", "completed", "cancelled"] = "pending"
    evidence_message_ids: list[int] = Field(default_factory=list)

    @field_validator("evidence_message_ids", mode="after")
    @classmethod
    def _limit_evidence_message_ids(cls, values: list[int]) -> list[int]:
        return values[:10]


class SummaryEvidence(BaseModel):
    field: str
    message_ids: list[int] = Field(default_factory=list)
    source_role: Literal["customer", "sale", "agent"]

    @field_validator("message_ids", mode="after")
    @classmethod
    def _limit_message_ids(cls, values: list[int]) -> list[int]:
        return values[:10]


class CustomerSummaryMetadata(BaseModel):
    needs: CustomerNeeds = Field(default_factory=CustomerNeeds)
    considered_units: list[ConsideredUnit] = Field(default_factory=list)
    objections: list[str] = Field(default_factory=list)
    pending_questions: list[str] = Field(default_factory=list)
    commitments: list[SaleCommitment] = Field(default_factory=list)
    sentiment: str | None = None
    urgency: str | None = None
    next_best_actions: list[str] = Field(default_factory=list)
    evidence: list[SummaryEvidence] = Field(default_factory=list)

    @field_validator("considered_units", "objections", "pending_questions", "commitments", mode="after")
    @classmethod
    def _limit_twenty_item_sections(cls, values: list) -> list:
        return values[:20]

    @field_validator("next_best_actions", mode="after")
    @classmethod
    def _limit_next_best_actions(cls, values: list[str]) -> list[str]:
        return values[:10]

    @field_validator("evidence", mode="after")
    @classmethod
    def _limit_evidence(cls, values: list[SummaryEvidence]) -> list[SummaryEvidence]:
        return values[:50]


class CustomerSummarySnapshot(BaseModel):
    """Schema-constrained output produced by Gemini after applying one message batch."""

    summary_text: str
    metadata: CustomerSummaryMetadata


class CustomerConversationSummaryResponse(BaseModel):
    customer_id: int
    customer_label: str
    summary_text: str
    metadata: CustomerSummaryMetadata
    last_processed_message_id: int
    source_message_count: int
    newly_processed_message_count: int = 0
    generated_at: datetime
    schema_version: str
    model_name: str
    from_cache: bool = False
    is_stale: bool = False


class LiveInboxEntry(BaseModel):
    """One row in the Sale-facing "Khách đang chờ" queue (routers/sale_live.py)."""

    session_id: int
    customer_label: str
    last_message_preview: str
    waiting_since: datetime | None

    lead_tier: LeadTier = LeadTier.COLD
    lead_score: int = 0
    lead_reason: str | None = None
    customer_name: str | None = None
    customer_phone: str | None = None


class LeadSignalDetail(BaseModel):
    """One fired scoring signal, for the full breakdown panel on the chat screen itself.

    `LiveInboxEntry.lead_reason` (a single joined string) is enough for a queue row; the
    chat screen has room for the actual evidence — this is that evidence, one row per
    signal that fired, so a Sale can check the tier rather than just trust it.
    """

    label: str
    points: int


class LeadDetailResponse(BaseModel):
    """Full lead breakdown for the Sale actually talking to this customer right now.

    `null` when nobody has scored this session yet (e.g. the very first message of a fresh
    live handoff) — the frontend renders an explicit "chưa có dữ liệu" state rather than a
    misleading COLD badge with zero evidence behind it.
    """

    customer_label: str
    customer_name: str | None = None
    customer_phone: str | None = None

    lead_tier: LeadTier
    lead_score: int
    rule_score: int
    soft_score: int | None = None
    urgency: LeadUrgency | None = None
    purpose: LeadPurpose | None = None
    confidence: float | None = None
    detection_method: str

    turn_count: int
    scored_at: datetime | None = None

    signals: list[LeadSignalDetail] = []
    llm_reason: str | None = None

    next_action: str = ""
    budgets: list[str] = []
    unit_types: list[str] = []
    projects: list[str] = []


class SaleLiveMessageRequest(BaseModel):
    content: ChatText


class SaleSuggestResponse(BaseModel):
    """A draft answer for the Sale to review/edit — never persisted as a message until the
    Sale actually sends it via POST /sale/live-inbox/{id}/reply."""

    draft: str
    requires_hitl: bool = False
