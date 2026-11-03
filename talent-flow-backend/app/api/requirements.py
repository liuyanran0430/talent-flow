import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.common import ApiResponse
from ..schemas.requirement import (
    RecalculatePayload,
    RequirementBatchCreate,
    RequirementItemCreate,
    RequirementItemGen,
    RequirementItemOut,
    RequirementItemUpdate,
)
from ..services.recalculate_service import count_recalculable_candidates, recalc_job_candidates
from ..services.requirement_service import (
    RequirementGenerateEmptyError,
    RequirementJdEmptyError,
    RequirementNotFoundError,
    RequirementService,
)
from ..core.logging_config import (
    get_audit_logger,
    get_logger,
    get_trace_id,
)

logger = get_logger("requirements")
audit = get_audit_logger("requirement")

router = APIRouter(prefix="/requirements", tags=["requirements"])


@router.get(
    "/{job_id}/items",
    response_model=ApiResponse[list[RequirementItemOut]],
    summary="职位要求项列表",
)
def list_items(job_id: int, db: Session = Depends(get_db)):
    items = RequirementService(db).list_by_job(job_id)
    return ApiResponse.ok(items)


@router.post(
    "/{job_id}/generate",
    response_model=ApiResponse[list[RequirementItemGen]],
    summary="基于职位JD（description）调用LLM生成要求项（仅预览，不落库；确认后经 items/batch 应用）",
)
def generate_from_jd(job_id: int, db: Session = Depends(get_db)):
    try:
        items = RequirementService(db).generate_from_jd(job_id)
    except RequirementNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    except RequirementJdEmptyError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "该职位未填写职位要求（JD），无法生成")
    except RequirementGenerateEmptyError:
        logger.warning("JD 生成要求项结果为空 job_id=%s", job_id)
        audit.warning("要求项生成结果为空 job_id=%s", job_id)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "JD 解析结果为空，请重试")
    except Exception as e:
        logger.exception("JD 生成要求项失败 job_id=%s: %s", job_id, e)
        audit.error("要求项生成失败 job_id=%s error=%s", job_id, e)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"JD 解析失败：{e}")
    logger.info("JD生成要求项成功 job_id=%s items=%s", job_id, len(items))
    audit.info("要求项生成成功 job_id=%s items=%s names=%s", job_id, len(items), [i.name for i in items])
    return ApiResponse.ok(items)


@router.post(
    "/{job_id}/items/batch",
    response_model=ApiResponse[list[RequirementItemOut]],
    summary="批量覆盖写入要求项（AI 生成结果编辑确认后应用，整体覆盖当前职位要求）",
)
def batch_create_items(job_id: int, payload: RequirementBatchCreate, db: Session = Depends(get_db)):
    try:
        items = RequirementService(db).batch_replace(job_id, payload.items)
    except RequirementNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    audit.info("要求项批量覆盖 job_id=%s items=%s names=%s", job_id, len(items), [i.name for i in items])
    return ApiResponse.ok(items)


@router.post(
    "/{job_id}/recalculate",
    response_model=ApiResponse[dict],
    summary="要求配置变化后重算相关候选人：后台重新解析生成匹配建议（jobfits）并按算法参数重算AI得分（matches）",
)
def recalculate_candidates(
    job_id: int,
    background_tasks: BackgroundTasks,
    payload: RecalculatePayload | None = None,
    db: Session = Depends(get_db),
):
    svc = RequirementService(db)
    try:
        svc.ensure_job_exists(job_id)
    except RequirementNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    count = count_recalculable_candidates(db, job_id)
    if count == 0:
        return ApiResponse.ok({"count": 0}, message="no parsed candidates to recalculate")
    task_id = uuid.uuid4().hex[:8]
    logger.info("要求配置重算启动 job_id=%s candidates=%s", job_id, count)
    audit.info("要求重算触发 job_id=%s candidates=%s", job_id, count)
    background_tasks.add_task(
        recalc_job_candidates,
        job_id,
        payload or RecalculatePayload(),
        task_id,
        get_trace_id(),
    )
    return ApiResponse.ok({"count": count}, message="recalculating")


@router.post(
    "/{job_id}/items",
    response_model=ApiResponse[RequirementItemOut],
    status_code=status.HTTP_201_CREATED,
    summary="新增要求项",
)
def create_item(job_id: int, payload: RequirementItemCreate, db: Session = Depends(get_db)):
    payload = payload.model_copy(update={"job_id": job_id})
    try:
        item = RequirementService(db).create(payload)
    except RequirementNotFoundError:
        audit.warning("要求项新增失败：职位不存在 job_id=%s", job_id)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    audit.info("要求项新增 job_id=%s item_id=%s name=%s type=%s importance=%s", job_id, item.id, item.name, item.type, item.importance)
    return ApiResponse.ok(item)


@router.put(
    "/items/{item_id}",
    response_model=ApiResponse[RequirementItemOut],
    summary="更新要求项",
)
def update_item(item_id: int, payload: RequirementItemUpdate, db: Session = Depends(get_db)):
    try:
        item = RequirementService(db).update(item_id, payload)
    except RequirementNotFoundError:
        audit.warning("要求项更新失败：不存在 item_id=%s", item_id)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "requirement item not found")
    audit.info("要求项更新 item_id=%s job_id=%s fields=%s", item_id, item.job_id, list(payload.model_dump(exclude_unset=True).keys()))
    return ApiResponse.ok(item)


@router.delete(
    "/items/{item_id}",
    response_model=ApiResponse[None],
    summary="删除要求项",
)
def delete_item(item_id: int, db: Session = Depends(get_db)):
    try:
        RequirementService(db).delete(item_id)
    except RequirementNotFoundError:
        audit.warning("要求项删除失败：不存在 item_id=%s", item_id)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "requirement item not found")
    audit.info("要求项删除 item_id=%s", item_id)
    return ApiResponse.ok(None, message="deleted")
