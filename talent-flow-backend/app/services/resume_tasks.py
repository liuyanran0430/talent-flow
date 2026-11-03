"""简历解析后台任务：LLM 解析 + 结果落库编排。

与 services/resume_parser.py 的区别：resume_parser 是纯 LLM 解析（无 DB），
本模块负责把解析结果写回候选人/简历/匹配建议，由后台任务调用。
"""

import json
import uuid

from ..database import SessionLocal
from ..core.logging_config import (
    get_audit_logger,
    get_logger,
    reset_task_id,
    reset_trace_id,
    set_task_id,
    set_trace_id,
)
from ..repositories import CandidateRepository, JobFitRepository, RequirementRepository
from ..models.jobfit import JobFit
from .resume_parser import parse_resume

logger = get_logger("resumes")
audit = get_audit_logger("resume")


def run_parse(
    candidate_id: int,
    preserve_status: bool = False,
    task_id: str | None = None,
    trace_id: str | None = None,
) -> None:
    """后台解析任务：调用 LLM 解析简历，写回基本信息并生成职位匹配建议（jobfits）。

    :param preserve_status: 要求配置变化触发的重算场景下保持原状态（finish 不降级回 review）
    :param task_id: 任务 id，用于区分同一 trace 下的多个异步任务（未传则自动生成）
    :param trace_id: 触发请求的 trace id，后台任务延续同一 trace_id 记录日志
    """
    task_id = task_id or uuid.uuid4().hex[:8]
    trace_token = set_trace_id(trace_id) if trace_id else None
    task_token = set_task_id(task_id)
    db = SessionLocal()
    try:
        cand_repo = CandidateRepository(db)
        req_repo = RequirementRepository(db)
        fit_repo = JobFitRepository(db)

        cand = cand_repo.get(candidate_id)
        resume = cand.resume if cand else None
        if not cand or not resume or not resume.resume_path:
            audit.warning("简历解析跳过 candidate_id=%s 原因=候选人/简历不存在", candidate_id)
            return
        job_id = resume.job_id
        prev_status = cand.status
        audit.info(
            "简历解析开始 candidate_id=%s job_id=%s preserve_status=%s",
            candidate_id, job_id, preserve_status,
        )

        # 该职位的要求项（含判定标准），作为匹配依据
        reqs = req_repo.list_by_job(job_id) if job_id else []

        try:
            result = json.loads(parse_resume(resume.resume_path, reqs))
        except Exception as e:
            logger.exception("简历解析失败 candidate_id=%s: %s", candidate_id, e)
            audit.error(
                "简历解析失败 candidate_id=%s job_id=%s error=%s",
                candidate_id, job_id, e,
            )
            if preserve_status and prev_status == "finish":
                cand.status = "finish"
                resume.info = "简历重新解析失败，保留原匹配建议"
            else:
                cand.status = "review"
                resume.info = "简历解析失败，请手动补全信息"
            cand_repo.commit()
            return

        basic = result.get("basic") or {}
        if basic.get("name"):
            cand.name = basic["name"]
        if basic.get("phone"):
            cand.phone = basic["phone"]
        if basic.get("email"):
            cand.email = basic["email"]
        if basic.get("experience"):
            resume.experience = basic["experience"]

        # 优势/风险：整体分析结论，序列化后存入 ResumeInfo.analysis
        resume.analysis = json.dumps(
            {
                "advantages": result.get("advantages") or [],
                "risks": result.get("risks") or [],
            },
            ensure_ascii=False,
        )
        if preserve_status and prev_status == "finish":
            cand.status = "finish"
            resume.info = "要求配置变化，已重新计算匹配建议"
        else:
            cand.status = "review"
            resume.info = "简历解析完成"

        # 覆盖式写入匹配建议：先清旧记录，再按名称对齐要求项落库
        saved_fits = 0
        if job_id:
            fit_repo.delete_by_candidate(cand.id)
            item_by_name = {r.name: r for r in reqs}
            for s in result.get("suggestions") or []:
                item = item_by_name.get(s.get("name"))
                if not item:
                    continue
                fit_repo.add(
                    JobFit(
                        candidate_id=cand.id,
                        requirement_item_id=item.id,
                        suggestion=s.get("suggestion") or "证据不足",
                        evidence=s.get("evidence") or "",
                    )
                )
                saved_fits += 1
        cand_repo.commit()
        audit.info(
            "简历解析完成 candidate_id=%s job_id=%s status=%s suggestions=%s",
            cand.id, job_id, cand.status, saved_fits,
        )
    finally:
        reset_task_id(task_token)
        if trace_token is not None:
            reset_trace_id(trace_token)
        db.close()
