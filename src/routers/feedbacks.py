from fastapi import APIRouter

from src.routers.dependencies import OrderFeedbacksServiceDep
from src.schemas.feedbacks import FeedbackCreate, FeedbackRead

router = APIRouter(prefix="/feedbacks", tags=["feedbacks"])


@router.post("/", response_model=FeedbackRead, status_code=201)
async def create_feedback(
    data: FeedbackCreate,
    service: OrderFeedbacksServiceDep,
) -> FeedbackRead:
    return await service.create_feedback(data)
