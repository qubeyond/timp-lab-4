from typing import Annotated

from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from src.api.deps import get_current_user
from src.api.limiter import limiter
from src.config import settings
from src.services.feedback import FeedbackService

router = APIRouter(prefix="/feedback", tags=["feedback"])


class FeedbackRequest(BaseModel):
    message: str = Field(min_length=3, max_length=2000)
    room_id: str | None = Field(default=None, max_length=16)


class FeedbackResponse(BaseModel):
    status: str = Field(default="sent")


@router.post("", response_model=FeedbackResponse)
@limiter.limit(settings.rate_limit_feedback)
@inject
async def send_feedback(
    request: Request,
    payload: FeedbackRequest,
    user: Annotated[dict, Depends(get_current_user)],
    feedback_service: FromDishka[FeedbackService],
):
    await feedback_service.report(payload.message, payload.room_id, user.get("sub"))
    return FeedbackResponse()
