from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..core.logging_config import get_audit_logger, get_logger
from ..database import get_db
from ..schemas.common import ApiResponse
from ..schemas.kb import (
    KbImportRequest,
    KbImportResult,
    KbReindexResult,
    KbSearchResult,
    KbStandardCreate,
    KbStandardOut,
    KbStandardUpdate,
)
from ..services.kb_service import KbStandardService, KbValidationError

router = APIRouter(prefix="/kb", tags=["kb"])

logger = get_logger("kb")
audit = get_audit_logger("kb")


def _bad_request(e: KbValidationError) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


@router.get(
    "/standards",
    response_model=ApiResponse[list[KbStandardOut]],
    summary="岗位标准条目列表（支持关键字/分类/状态筛选）",
)
def list_standards(
    q: str | None = Query(None, description="关键字，匹配名称/编码/别名/判定标准"),
    category: str | None = Query(None, description="分类：技能/经验/学历/证书/软素质"),
    status_filter: str | None = Query(None, alias="status", description="draft/published/archived"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    items = KbStandardService(db).list(q, category, status_filter, limit, offset)
    return ApiResponse.ok(items)


@router.get(
    "/standards/{standard_id}",
    response_model=ApiResponse[KbStandardOut],
    summary="岗位标准条目详情",
)
def get_standard(standard_id: int, db: Session = Depends(get_db)):
    item = KbStandardService(db).get(standard_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "standard not found")
    return ApiResponse.ok(item)


@router.post(
    "/standards",
    response_model=ApiResponse[KbStandardOut],
    status_code=status.HTTP_201_CREATED,
    summary="新建岗位标准（草稿，需发布后才进入检索）",
)
def create_standard(payload: KbStandardCreate, db: Session = Depends(get_db)):
    try:
        item = KbStandardService(db).create(payload)
    except KbValidationError as e:
        audit.warning("岗位标准新增失败：%s", e)
        raise _bad_request(e)
    audit.info("岗位标准新增 id=%s code=%s name=%s", item.id, item.code, item.name)
    return ApiResponse.ok(item)


@router.put(
    "/standards/{standard_id}",
    response_model=ApiResponse[KbStandardOut],
    summary="更新岗位标准（已发布条目更新会自动升版并重新向量化）",
)
def update_standard(standard_id: int, payload: KbStandardUpdate, db: Session = Depends(get_db)):
    try:
        item = KbStandardService(db).update(standard_id, payload)
    except KbValidationError as e:
        audit.warning("岗位标准更新失败 standard_id=%s：%s", standard_id, e)
        raise _bad_request(e)
    audit.info("岗位标准更新 id=%s fields=%s version=%s", item.id, list(payload.model_dump(exclude_unset=True).keys()), item.version)
    return ApiResponse.ok(item)


@router.post(
    "/standards/{standard_id}/publish",
    response_model=ApiResponse[KbStandardOut],
    summary="发布标准并写入向量索引",
)
def publish_standard(standard_id: int, db: Session = Depends(get_db)):
    try:
        item = KbStandardService(db).publish(standard_id)
    except KbValidationError as e:
        raise _bad_request(e)
    audit.info("岗位标准发布 id=%s name=%s version=%s", item.id, item.name, item.version)
    return ApiResponse.ok(item, message="published")


@router.post(
    "/standards/{standard_id}/archive",
    response_model=ApiResponse[KbStandardOut],
    summary="归档标准并移除向量索引",
)
def archive_standard(standard_id: int, db: Session = Depends(get_db)):
    try:
        item = KbStandardService(db).archive(standard_id)
    except KbValidationError as e:
        raise _bad_request(e)
    audit.info("岗位标准归档 id=%s name=%s", item.id, item.name)
    return ApiResponse.ok(item, message="archived")


@router.delete(
    "/standards/{standard_id}",
    response_model=ApiResponse[None],
    summary="删除标准（同时移除向量索引）",
)
def delete_standard(standard_id: int, db: Session = Depends(get_db)):
    try:
        KbStandardService(db).delete(standard_id)
    except KbValidationError as e:
        raise _bad_request(e)
    audit.info("岗位标准删除 id=%s", standard_id)
    return ApiResponse.ok(None, message="deleted")


@router.get(
    "/search",
    response_model=ApiResponse[KbSearchResult],
    summary="标准检索（调试与前端预览）",
)
def search_standards(
    q: str = Query(..., min_length=1, description="检索文本"),
    top_k: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    return ApiResponse.ok(KbStandardService(db).search(q, top_k))


@router.post(
    "/import/requirements",
    response_model=ApiResponse[KbImportResult],
    summary="从历史职位要求项沉淀标准草稿（重名自动跳过）",
)
def import_from_requirements(payload: KbImportRequest, db: Session = Depends(get_db)):
    result = KbStandardService(db).import_from_requirements(payload)
    audit.info("岗位标准历史沉淀 created=%s skipped=%s", result.created, result.skipped)
    return ApiResponse.ok(result)


@router.post(
    "/reindex",
    response_model=ApiResponse[KbReindexResult],
    summary="全量重建标准向量索引（MySQL 为事实源，可随时重建）",
)
def reindex(db: Session = Depends(get_db)):
    result = KbStandardService(db).reindex()
    logger.info("岗位标准索引重建 total=%s indexed=%s failed=%s", result.total, result.indexed, result.failed)
    return ApiResponse.ok(result)
