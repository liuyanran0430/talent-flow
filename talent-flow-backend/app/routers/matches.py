from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.common import ApiResponse
from ..schemas.match import MatchCreate, MatchOut, MatchUpdate
from ..services.match_service import MatchNotFoundError, MatchService

router = APIRouter(prefix="/matches", tags=["matches"])


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
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
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
        raise HTTPException(status.HTTP_404_NOT_FOUND, "match not found")
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
        raise HTTPException(status.HTTP_404_NOT_FOUND, "match not found")
    return ApiResponse.ok(None, message="deleted")
