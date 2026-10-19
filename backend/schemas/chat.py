from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel

from backend.ai.guardrails import normalize_user_input
from backend.core.config import get_settings
from backend.core.enums import FeedbackType, HitlStatus, MessageEmotion, MessageSender


class ChatSessionCreate(BaseModel):
    title: str | None = None
    customer_name: str | None = None
    project_id: str | None = None


class ChatSessionResponse(BaseModel):
    id: int
    sale_id: int | None
    title: str | None = None
    customer_name: str | None = None
    project_id: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


def _clean_chat_text(value: str) -> str:
    """Normalise a typed chat message and bound its length at the API boundary.

    Unbounded input is both a cost problem (every character is billed to the model, twice
    with the Verifier) and an attack surface (long payloads bury instructions far from the
    question). Read from settings at call time so tests and deployments can tune it.
    """
    cleaned = normalize_user_input(value)
    if not cleaned:
        raise ValueError("Nội dung tin nhắn không được để trống.")
    limit = get_settings().chat_max_query_chars
    if len(cleaned) > limit:
        raise ValueError(f"Tin nhắn quá dài (tối đa {limit} ký tự).")
    return cleaned


ChatText = Annotated[str, AfterValidator(_clean_chat_text)]


class Citation(BaseModel):
    document_id: int
    title: str
    qualifier: str | None = None
    page: int | None = None
    y_position: float | None = None


class AnswerImage(BaseModel):
    """One project photo shown in the swipeable strip under an answer."""

    url: str
    project_id: str
    project_name: str


class PropertyListing(BaseModel):
    """One recommended unit, rendered as its own card (with paging arrows between cards)
    instead of as a bullet line in `content` — see prompts.PropertyListing and
    agent_pipeline._resolve_listing_images, which is what fills in `image_urls`/
    `amenities`/`project_id`. All three default empty: a listing whose project/gallery
    could not be resolved is still shown, just without photos or amenity tags.

    `unit_code`/`status`/`tower` are non-empty only for a listing built from one confirmed
    TỒN KHO REAL-TIME record (see prompts.PropertyListing) — a catalogue-only
    project/subdivision summary card leaves all three "".

    `tower` is both what selected `image_urls` (see answer_images_service.select_listing_images)
    and what the card shows, so a viewer can check the photo against the tower it claims.
    """

    project_name: str
    unit_type: str
    area_range: str
    price_range: str
    image_urls: list[str] = []
    amenities: list[str] = []
    project_id: str | None = None
    unit_code: str = ""
    status: str = ""
    tower: str = ""


class MessageCreate(BaseModel):
    session_id: int | None = None
    content: str


class MessageResponse(BaseModel):
    id: int
    session_id: int | None = None
    sender: MessageSender
    content: str
    citations: list[Citation] | None = None
    images: list[AnswerImage] | None = None
    verifier_score: float | None = None
    requires_hitl: bool
    hitl_confirmed: bool = False
    emotion: MessageEmotion | None = None
    quick_replies: list[str] | None = None
    listings: list[PropertyListing] | None = None
    suggested_questions: list[str] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class HitlConfirmRequest(BaseModel):
    """Payload for the mandatory confirmation before an answer may be sent to a customer."""

    confirmed_content: str


class HitlLogResponse(BaseModel):
    id: int
    message_id: int
    sale_id: int
    status: HitlStatus
    confirmed_content: str | None = None
    confirmed_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class FeedbackCreate(BaseModel):
    """A Sale reporting an answer as wrong or incomplete."""

    message_id: int
    type: FeedbackType
    comment: str | None = None


class FeedbackResponse(BaseModel):
    id: int
    message_id: int
    user_id: int | None = None
    type: FeedbackType
    comment: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class FailedQuestion(BaseModel):
    """One row of the "Top câu hỏi AI trả lời thất bại" table in Admin Tab 2."""

    message_id: int
    question: str
    feedback_count: int
