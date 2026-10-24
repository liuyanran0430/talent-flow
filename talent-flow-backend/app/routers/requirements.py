import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import SessionLocal, get_db
from ..models import Candidate, Job, JobFit, Match, RequirementItem
from ..schemas.common import ApiResponse
from ..schemas.requirement import (
    RecalculatePayload,
    RequirementBatchCreate,
    RequirementItemCreate,
    RequirementItemGen,
    RequirementItemOut,
    RequirementItemUpdate,
)
from ..services.jd_parser import parse_jd
from ..services.requirement_service import RequirementNotFoundError, RequirementService
from ..routers.resumes import run_parse
from ..logging_config import get_logger

logger = get_logger("requirements")

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
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    if not job.description or not job.description.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "该职位未填写职位要求（JD），无法生成")
    try:
        json_str = parse_jd(job.description)
        data = json.loads(json_str)
        items = [RequirementItemGen(**it) for it in data.get("items", [])]
    except Exception as e:
        logging.getLogger("uvicorn.error").exception("JD generate failed for job %s", job_id)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"JD 解析失败：{e}")
    if not items:
        logging.getLogger("uvicorn.error").warning("JD generate returned empty items for job %s", job_id)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "JD 解析结果为空，请重试")
    logger.info("JD生成要求项成功 job_id=%s items=%s", job_id, len(items))
    return ApiResponse.ok(items)


@router.post(
    "/{job_id}/items/batch",
    response_model=ApiResponse[list[RequirementItemOut]],
    summary="批量覆盖写入要求项（AI 生成结果编辑确认后应用，整体覆盖当前职位要求）",
)
def batch_create_items(job_id: int, payload: RequirementBatchCreate, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    db.query(RequirementItem).filter(RequirementItem.job_id == job_id).delete()
    created = []
    for it in payload.items:
        item = RequirementItem(
            job_id=job_id,
            name=it.name.strip(),
            type=it.type,
            importance=it.importance,
            standard=it.standard,
        )
        db.add(item)
        db.flush()
        created.append(item)
    db.commit()
    return ApiResponse.ok([RequirementItemOut.model_validate(i) for i in created])


# ---------- 要求配置变化后的候选人重算 ----------

def _item_score(suggestion: str) -> float:
    """单项得分：满足=1，证据不足=0.5，不满足=0（与前端 matchScore.js 保持一致）"""
    if suggestion == "满足":
        return 1.0
    if suggestion == "证据不足":
        return 0.5
    return 0.0


def _calc_score(items: list[RequirementItem], fits: list[JobFit], params: RecalculatePayload) -> dict:
    """按前端 ALGO_SETTINGS 相同公式计算匹配得分与各建议项个数"""
    if not items or not fits:
        return {"score": 0, "must_satisfied": 0, "must_unsatisfied": 0, "must_insufficient": 0, "bonus_satisfied": 0}
    fit_map = {f.requirement_item_id: f.suggestion for f in fits}
    weights = params.weights

    must_weight_sum = 0.0
    must_earn = 0.0
    must_satisfied = must_unsatisfied = must_insufficient = bonus_satisfied = 0
    for it in items:
        suggestion = fit_map.get(it.id, "不满足")
        s = _item_score(suggestion)
        if it.type == "加分":
            if s == 1:
                bonus_satisfied += 1
        else:
            weight = weights.get(it.importance, 35)
            must_weight_sum += weight
            must_earn += weight * s
            if suggestion == "满足":
                must_satisfied += 1
            elif suggestion == "证据不足":
                must_insufficient += 1
            else:
                must_unsatisfied += 1

    if must_weight_sum == 0:
        return {"score": 0, "must_satisfied": must_satisfied, "must_unsatisfied": must_unsatisfied,
                "must_insufficient": must_insufficient, "bonus_satisfied": bonus_satisfied}

    must_total = must_satisfied + must_unsatisfied + must_insufficient
    base = (100 * must_earn) / must_weight_sum
    gate_pass = must_total == 0 or (must_satisfied / must_total) * 100 >= params.must_gate
    final = base if gate_pass else min(base, params.recommend_threshold - 1)
    final += min(6, 2 * bonus_satisfied)
    return {
        "score": max(0, min(100, round(final))),
        "must_satisfied": must_satisfied,
        "must_unsatisfied": must_unsatisfied,
        "must_insufficient": must_insufficient,
        "bonus_satisfied": bonus_satisfied,
    }


def _recalc_job_candidates(job_id: int, params: RecalculatePayload) -> None:
    """后台任务：串行重新解析该职位下已解析候选人（重建 jobfits），随后重算得分并写入 matches。"""
    db = SessionLocal()
    try:
        cand_ids = [
            c.id
            for c in db.query(Candidate)
            .filter(Candidate.job_id == job_id, Candidate.status.in_(["review", "finish"]))
            .all()
            if c.resume_path
        ]
        # 逐个重新解析：run_parse 内部自建会话并覆盖式重建 jobfits
        for cid in cand_ids:
            try:
                run_parse(cid, preserve_status=True)
            except Exception:
                logging.getLogger("uvicorn.error").exception(
                    "recalculate parse failed for candidate %s", cid
                )

        items = db.query(RequirementItem).filter(RequirementItem.job_id == job_id).all()
        for cid in cand_ids:
            try:
                fits = db.query(JobFit).filter(JobFit.candidate_id == cid).all()
                calc = _calc_score(items, fits, params)
                match = (
                    db.query(Match)
                    .filter(Match.candidate_id == cid, Match.job_id == job_id)
                    .first()
                )
                if match:
                    for k, v in calc.items():
                        setattr(match, k, v)
                else:
                    db.add(Match(candidate_id=cid, job_id=job_id, **calc))
            except Exception:
                logging.getLogger("uvicorn.error").exception(
                    "recalculate score failed for candidate %s", cid
                )
        db.commit()
        logger.info("要求配置重算完成 job_id=%s candidates=%s", job_id, len(cand_ids))
    finally:
        db.close()


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
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    count = (
        db.query(Candidate)
        .filter(
            Candidate.job_id == job_id,
            Candidate.status.in_(["review", "finish"]),
            Candidate.resume_path.isnot(None),
        )
        .count()
    )
    if count == 0:
        return ApiResponse.ok({"count": 0}, message="no parsed candidates to recalculate")
    logger.info("要求配置重算启动 job_id=%s candidates=%s", job_id, count)
    background_tasks.add_task(_recalc_job_candidates, job_id, payload or RecalculatePayload())
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
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
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
        raise HTTPException(status.HTTP_404_NOT_FOUND, "requirement item not found")
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
        raise HTTPException(status.HTTP_404_NOT_FOUND, "requirement item not found")
    return ApiResponse.ok(None, message="deleted")
