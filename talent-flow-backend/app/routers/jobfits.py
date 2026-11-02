from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..logging_config import get_audit_logger
from ..schemas.common import ApiResponse
from ..schemas.jobfit import JobFitCreate, JobFitOut, JobFitUpdate
from ..services.jobfit_service import JobFitNotFoundError, JobFitService

router = APIRouter(prefix="/jobfits", tags=["jobfits"])
audit = get_audit_logger("jobfit")


@router.get(
    "/candidates/{candidate_id}",
    response_model=ApiResponse[list[JobFitOut]],
    summary="候选人匹配建议列表",
)
def list_by_candidate(candidate_id: int, db: Session = Depends(get_db)):
    items = JobFitService(db).list_by_candidate(candidate_id)
    return ApiResponse.ok(items)


@router.post(
    "",
    response_model=ApiResponse[JobFitOut],
    status_code=status.HTTP_201_CREATED,
    summary="新增匹配建议",
)
def create_jobfit(payload: JobFitCreate, db: Session = Depends(get_db)):
    try:
        item = JobFitService(db).create(payload)
    except JobFitNotFoundError as e:
        audit.warning("匹配建议新增失败 candidate_id=%s item_id=%s error=%s", payload.candidate_id, payload.requirement_item_id, e)
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    audit.info(
        "匹配建议新增 id=%s candidate_id=%s requirement_item_id=%s suggestion=%s",
        item.id, item.candidate_id, item.requirement_item_id, item.suggestion,
    )
    return ApiResponse.ok(item)


@router.put(
    "/{item_id}",
    response_model=ApiResponse[JobFitOut],
    summary="更新匹配建议",
)
def update_jobfit(item_id: int, payload: JobFitUpdate, db: Session = Depends(get_db)):
    try:
        item = JobFitService(db).update(item_id, payload)
    except JobFitNotFoundError:
        audit.warning("匹配建议更新失败：不存在 id=%s", item_id)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "jobfit not found")
    audit.info(
        "匹配建议更新 id=%s candidate_id=%s requirement_item_id=%s suggestion=%s",
        item_id, item.candidate_id, item.requirement_item_id, item.suggestion,
    )
    return ApiResponse.ok(item)


@router.delete(
    "/{item_id}",
    response_model=ApiResponse[None],
    summary="删除匹配建议",
)
def delete_jobfit(item_id: int, db: Session = Depends(get_db)):
    try:
        JobFitService(db).delete(item_id)
    except JobFitNotFoundError:
        audit.warning("匹配建议删除失败：不存在 id=%s", item_id)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "jobfit not found")
    audit.info("匹配建议删除 id=%s", item_id)
    return ApiResponse.ok(None, message="deleted")
