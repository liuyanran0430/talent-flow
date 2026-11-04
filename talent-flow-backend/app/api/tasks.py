"""异步任务状态查询：前端凭接口返回的 request_id 轮询处理进度。"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.common import ApiResponse
from ..services.async_tasks import get_task_status

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get(
    "/{request_id}",
    response_model=ApiResponse[dict],
    summary="查询异步任务状态（pending/running/success/failed，success 时返回 result）",
)
def get_task(request_id: str, db: Session = Depends(get_db)):
    data = get_task_status(db, request_id)
    if not data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "task not found")
    return ApiResponse.ok(data)
