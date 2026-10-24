from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.candidate import CandidateCreate, CandidateOut, CandidateUpdate
from ..schemas.common import ApiResponse, PageResponse
from ..services.candidate_service import CandidateNotFoundError, CandidateService

router = APIRouter(prefix="/candidates", tags=["candidates"])


@router.get("", response_model=ApiResponse[PageResponse[CandidateOut]], summary="候选人分页列表")
def list_candidates(
    search: str | None = Query(None, description="按姓名模糊搜索"),
    candidate_status: str | None = Query(None, alias="status"),
    job_id: int | None = Query(None, description="按意向职位筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    items, total = CandidateService(db).list_candidates(
        search=search, status=candidate_status, job_id=job_id, page=page, page_size=page_size
    )
    return ApiResponse.ok(PageResponse(total=total, page=page, page_size=page_size, items=items))


@router.get("/{candidate_id}", response_model=ApiResponse[CandidateOut], summary="候选人详情")
def get_candidate(candidate_id: int, db: Session = Depends(get_db)):
    try:
        item = CandidateService(db).get_candidate(candidate_id)
    except CandidateNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "candidate not found")
    return ApiResponse.ok(item)


@router.post("", response_model=ApiResponse[CandidateOut], status_code=status.HTTP_201_CREATED, summary="新建候选人")
def create_candidate(payload: CandidateCreate, db: Session = Depends(get_db)):
    c = CandidateService(db).create_candidate(payload)
    return ApiResponse.ok(CandidateOut.model_validate(c))


@router.put("/{candidate_id}", response_model=ApiResponse[CandidateOut], summary="更新候选人")
def update_candidate(candidate_id: int, payload: CandidateUpdate, db: Session = Depends(get_db)):
    try:
        c = CandidateService(db).update_candidate(candidate_id, payload)
    except CandidateNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "candidate not found")
    return ApiResponse.ok(CandidateOut.model_validate(c))


@router.delete("/{candidate_id}", response_model=ApiResponse[None], summary="删除候选人")
def delete_candidate(candidate_id: int, db: Session = Depends(get_db)):
    try:
        CandidateService(db).delete_candidate(candidate_id)
    except CandidateNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "candidate not found")
    return ApiResponse.ok(None, message="deleted")
