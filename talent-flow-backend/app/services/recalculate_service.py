"""要求配置变化后的候选人重算：后台任务。

流程：串行重新解析该职位下已解析候选人（重建 jobfits）→ 按算法参数重算得分写入 matches。
"""

import uuid

from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..core.logging_config import (
    get_audit_logger,
    get_logger,
    get_trace_id,
    reset_task_id,
    reset_trace_id,
    set_task_id,
    set_trace_id,
)
from ..models import Match
from ..repositories import CandidateRepository, JobFitRepository, MatchRepository, RequirementRepository
from ..schemas.requirement import RecalculatePayload
from .resume_tasks import run_parse
from .scoring import calc_match_score

logger = get_logger("requirements")
audit = get_audit_logger("requirement")


def count_recalculable_candidates(db: Session, job_id: int) -> int:
    """某职位下可重算（已解析且简历文件存在）的候选人数。"""
    return CandidateRepository(db).count_recalculable(job_id)


def recalc_job_candidates(
    job_id: int,
    params: RecalculatePayload,
    task_id: str | None = None,
    trace_id: str | None = None,
) -> None:
    """后台任务：串行重新解析该职位下已解析候选人（重建 jobfits），随后重算得分并写入 matches。"""
    task_id = task_id or uuid.uuid4().hex[:8]
    trace_token = set_trace_id(trace_id) if trace_id else None
    task_token = set_task_id(task_id)
    db = SessionLocal()
    try:
        cand_repo = CandidateRepository(db)
        req_repo = RequirementRepository(db)
        fit_repo = JobFitRepository(db)
        match_repo = MatchRepository(db)

        cand_ids = [
            c.id
            for c in cand_repo.list_parsed_by_job(job_id)
            if c.resume and c.resume.resume_path
        ]
        audit.info("要求重算开始 job_id=%s candidates=%s", job_id, len(cand_ids))
        # 逐个重新解析：run_parse 内部自建会话并覆盖式重建 jobfits（沿用同一 trace 与 task）
        parse_failed = 0
        for cid in cand_ids:
            try:
                run_parse(cid, preserve_status=True, task_id=task_id, trace_id=get_trace_id())
            except Exception as e:
                parse_failed += 1
                logger.exception("要求重算：候选人简历解析失败 candidate_id=%s: %s", cid, e)
                audit.error("要求重算解析失败 job_id=%s candidate_id=%s error=%s", job_id, cid, e)

        items = req_repo.list_by_job(job_id)
        score_failed = 0
        for cid in cand_ids:
            try:
                fits = fit_repo.list_by_candidate(cid)
                calc = calc_match_score(items, fits, params)
                match = match_repo.get_by_candidate_job(cid, job_id)
                if match:
                    for k, v in calc.items():
                        setattr(match, k, v)
                else:
                    match_repo.add(Match(candidate_id=cid, job_id=job_id, **calc))
            except Exception as e:
                score_failed += 1
                logger.exception("要求重算：候选人打分失败 candidate_id=%s: %s", cid, e)
                audit.error("要求重算打分失败 job_id=%s candidate_id=%s error=%s", job_id, cid, e)
        match_repo.commit()
        logger.info("要求配置重算完成 job_id=%s candidates=%s", job_id, len(cand_ids))
        audit.info(
            "要求重算完成 job_id=%s candidates=%s parse_failed=%s score_failed=%s",
            job_id, len(cand_ids), parse_failed, score_failed,
        )
    finally:
        reset_task_id(task_token)
        if trace_token is not None:
            reset_trace_id(trace_token)
        db.close()
