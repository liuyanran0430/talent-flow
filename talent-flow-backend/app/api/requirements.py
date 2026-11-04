from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.common import ApiResponse
from ..schemas.requirement import (
    RecalculatePayload,
    RequirementBatchCreate,
    RequirementItemCreate,
    RequirementItemOut,
    RequirementItemUpdate,
)
from ..services.async_tasks import create_task, execute_task
from ..services.recalculate_service import count_recalculable_candidates, recalc_job_candidates
from ..services.requirement_service import (
    RequirementJdEmptyError,
    RequirementNotFoundError,
    RequirementService,
    run_generate_preview,
)
from ..core.logging_config import (
    get_audit_logger,
    get_logger,
    set_request_id,
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
    response_model=ApiResponse[dict],
    summary="基于职位JD异步调用LLM生成要求项：立即返回 request_id，前端凭该 id 轮询 GET /tasks/{request_id}",
)
def generate_from_jd(job_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    # 前置校验同步完成（不调用 LLM），职位不存在/JD 为空可立即返回错误
    try:
        RequirementService(db).ensure_jd_available(job_id)
    except RequirementNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    except RequirementJdEmptyError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "该职位未填写职位要求（JD），无法生成")

    request_id = create_task(db, "requirement_generate")
    # 触发接口属于 LLM 相关接口，绑定 request_id，本次请求的日志与访问日志都带上它
    set_request_id(request_id)
    logger.info("要求项生成任务已入队 job_id=%s request_id=%s", job_id, request_id)
    audit.info("要求项生成触发 job_id=%s request_id=%s", job_id, request_id)
    background_tasks.add_task(execute_task, request_id, lambda: run_generate_preview(job_id))
    return ApiResponse.ok({"request_id": request_id}, message="generating")


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
    summary="要求配置变化后异步重算：立即返回 request_id，前端凭该 id 轮询 GET /tasks/{request_id}",
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

    request_id = create_task(db, "requirement_recalculate")
    # 触发接口属于 LLM 相关接口，绑定 request_id，本次请求的日志与访问日志都带上它
    set_request_id(request_id)
    params = payload or RecalculatePayload()
    logger.info("要求配置重算任务已入队 job_id=%s candidates=%s request_id=%s", job_id, count, request_id)
    audit.info("要求重算触发 job_id=%s candidates=%s request_id=%s", job_id, count, request_id)
    background_tasks.add_task(
        execute_task,
        request_id,
        lambda: _run_recalc(job_id, params, request_id, count),
    )
    return ApiResponse.ok({"count": count, "request_id": request_id}, message="recalculating")


def _run_recalc(job_id: int, params: RecalculatePayload, request_id: str, count: int) -> dict:
    """后台任务入口：重算完成后把处理人数作为结果落库。"""
    recalc_job_candidates(job_id, params, request_id=request_id)
    return {"count": count}


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
