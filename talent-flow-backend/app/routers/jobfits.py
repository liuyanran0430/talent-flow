from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.common import ApiResponse
from ..schemas.jobfit import JobFitCreate, JobFitOut, JobFitUpdate
from ..services.jobfit_service import JobFitNotFoundError, JobFitService

router = APIRouter(prefix="/jobfits", tags=["jobfits"])


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
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
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
        raise HTTPException(status.HTTP_404_NOT_FOUND, "jobfit not found")
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
        raise HTTPException(status.HTTP_404_NOT_FOUND, "jobfit not found")
    return ApiResponse.ok(None, message="deleted")
