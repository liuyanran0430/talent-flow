from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..logging_config import get_audit_logger
from ..schemas.common import ApiResponse
from ..schemas.match import MatchCreate, MatchOut, MatchUpdate
from ..services.match_service import MatchNotFoundError, MatchService

router = APIRouter(prefix="/matches", tags=["matches"])
audit = get_audit_logger("match")


@router.get(
    "/candidates/{candidate_id}",
    response_model=ApiResponse[list[MatchOut]],
    summary="候选人的岗位匹配打分列表",
)
def list_by_candidate(candidate_id: int, db: Session = Depends(get_db)):
    items = MatchService(db).list_by_candidate(candidate_id)
    return ApiResponse.ok(items)


@router.post(
    "",
    response_model=ApiResponse[MatchOut],
    status_code=status.HTTP_201_CREATED,
    summary="新增匹配打分",
)
def create_match(payload: MatchCreate, db: Session = Depends(get_db)):
    try:
        item = MatchService(db).create(payload)
    except MatchNotFoundError as e:
        audit.warning("匹配打分新增失败 job_id=%s candidate_id=%s error=%s", payload.job_id, payload.candidate_id, e)
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    audit.info(
        "匹配打分新增 id=%s job_id=%s candidate_id=%s score=%s",
        item.id, item.job_id, item.candidate_id, item.score,
    )
    return ApiResponse.ok(item)


@router.put(
    "/{item_id}",
    response_model=ApiResponse[MatchOut],
    summary="更新匹配打分",
)
def update_match(item_id: int, payload: MatchUpdate, db: Session = Depends(get_db)):
    try:
        item = MatchService(db).update(item_id, payload)
    except MatchNotFoundError:
        audit.warning("匹配打分更新失败：不存在 id=%s", item_id)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "match not found")
    audit.info(
        "匹配打分更新 id=%s job_id=%s candidate_id=%s score=%s",
        item_id, item.job_id, item.candidate_id, item.score,
    )
    return ApiResponse.ok(item)


@router.delete(
    "/{item_id}",
    response_model=ApiResponse[None],
    summary="删除匹配打分",
)
def delete_match(item_id: int, db: Session = Depends(get_db)):
    try:
        MatchService(db).delete(item_id)
    except MatchNotFoundError:
        audit.warning("匹配打分删除失败：不存在 id=%s", item_id)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "match not found")
    audit.info("匹配打分删除 id=%s", item_id)
    return ApiResponse.ok(None, message="deleted")
