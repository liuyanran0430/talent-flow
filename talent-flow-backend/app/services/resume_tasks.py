"""简历解析后台任务：LLM 解析 + 结果落库编排。

与 services/resume_parser.py 的区别：resume_parser 是纯 LLM 解析（无 DB），
本模块负责把解析结果写回候选人/简历/匹配建议，由后台任务调用。
"""

import json
import threading
import uuid

from ..database import SessionLocal
from ..core.logging_config import (
    get_audit_logger,
    get_logger,
    reset_request_id,
    reset_retrieval_ids,
    set_request_id,
    set_retrieval_ids,
)
from ..repositories import (
    CandidateRepository,
    JobFitRepository,
    KbStandardRepository,
    RequirementRepository,
)
from ..models.jobfit import JobFit
from .requirement_service import (
    RequirementGenerateEmptyError,
    RequirementJdEmptyError,
    RequirementService,
)
from .resume_parser import parse_resume

logger = get_logger("resumes")
audit = get_audit_logger("resume")


class ParseAlreadyRunningError(RuntimeError):
    """同一候选人的简历解析已在执行，本次触发被单飞去重跳过"""


# 进程内单飞锁：candidate_id → 执行中的锁。后台任务在独立线程中运行，
# 这里保证同一候选人在同一进程内同一时刻只有一个解析在跑；
# 跨进程的并发抢占由 candidate.status 的条件更新（mark_parsing）兜底。
_parse_locks: dict[int, threading.Lock] = {}
_parse_locks_guard = threading.Lock()


def _try_acquire_parse(candidate_id: int) -> threading.Lock | None:
    """非阻塞获取解析权；已有解析在执行时返回 None。"""
    with _parse_locks_guard:
        if candidate_id in _parse_locks:
            return None
        lock = threading.Lock()
        _parse_locks[candidate_id] = lock
    lock.acquire()
    return lock


def _release_parse(candidate_id: int, lock: threading.Lock) -> None:
    with _parse_locks_guard:
        # 只移除自己持有的那把锁，避免误删后续持锁者登记的锁
        if _parse_locks.get(candidate_id) is lock:
            _parse_locks.pop(candidate_id, None)
    lock.release()


def _enrich_requirements_with_standards(db, reqs) -> tuple[list[dict], list[int]]:
    """把要求项转换为解析器入参，并注入关联标准条目的判定标准与证据要求。

    :return: (解析器入参列表, 本次实际注入的标准 id 列表)；标准 id 会写入 LLM 结构化日志 retrieval_ids
    """
    ids = [r.standard_id for r in reqs if r.standard_id]
    standards = (
        {s.id: s for s in KbStandardRepository(db).list_published_by_ids(ids)} if ids else {}
    )
    payload: list[dict] = []
    used_ids: list[int] = []
    for req in reqs:
        item: dict = {"name": req.name, "standard": req.standard}
        standard = standards.get(req.standard_id) if req.standard_id else None
        if standard:
            item["standard_ref"] = standard.standard
            item["required_evidence"] = standard.required_evidence
            used_ids.append(standard.id)
        payload.append(item)
    return payload, used_ids


def _auto_generate_requirements(db, job_id: int, req_repo: RequirementRepository) -> list:
    """职位未配置要求项时，自动从 JD 提取并持久化要求项。

    提取成功则返回持久化后的要求项列表；失败（JD 为空/LLM 异常等）返回空列表，
    主流程降级为无要求项匹配（不阻断简历解析）。
    """
    try:
        logger.info("职位 %s 无要求项，自动从 JD 提取", job_id)
        gen_items = RequirementService(db).generate_from_jd(job_id)
        if not gen_items:
            logger.warning("职位 %s 从 JD 提取要求项结果为空", job_id)
            return []
        req_repo.bulk_create(
            job_id,
            [
                {
                    "name": it.name,
                    "type": it.type,
                    "importance": it.importance,
                    "standard": it.standard,
                    "standard_id": it.standard_id,
                }
                for it in gen_items
            ],
        )
        req_repo.commit()
        reqs = req_repo.list_by_job(job_id)
        audit.info("职位 %s 自动生成要求项 %s 条", job_id, len(reqs))
        return reqs
    except RequirementJdEmptyError:
        logger.warning("职位 %s 未填写 JD，无法自动生成要求项", job_id)
    except RequirementGenerateEmptyError:
        logger.warning("职位 %s JD 提取要求项结果为空", job_id)
    except Exception:
        logger.exception("职位 %s 自动生成要求项异常", job_id)
    return []


def run_parse(
    candidate_id: int,
    preserve_status: bool = False,
    request_id: str | None = None,
) -> bool:
    """后台解析任务：调用 LLM 解析简历，写回基本信息并生成职位匹配建议（jobfits）。

    :param preserve_status: 要求配置变化触发的重算场景下保持原状态（finish 不降级回 review）
    :param request_id: 接口返回给前端的异步任务 id，日志与 LLM 结构化记录沿用该 id
    :return: 解析是否成功；失败时已把候选人置为 review 等待人工复核
    :raises ParseAlreadyRunningError: 同一候选人已有解析在执行，本次触发被去重跳过
    """
    request_id = request_id or uuid.uuid4().hex[:8]
    lock = _try_acquire_parse(candidate_id)
    if lock is None:
        audit.warning(
            "简历解析去重跳过 candidate_id=%s 原因=同候选人已有解析在执行", candidate_id
        )
        raise ParseAlreadyRunningError(f"candidate {candidate_id} 已有解析在执行")

    request_token = set_request_id(request_id)
    db = SessionLocal()
    try:
        cand_repo = CandidateRepository(db)
        req_repo = RequirementRepository(db)
        fit_repo = JobFitRepository(db)

        cand = cand_repo.get(candidate_id)
        resume = cand.resume if cand else None
        if not cand or not resume or not resume.resume_path:
            audit.warning("简历解析跳过 candidate_id=%s 原因=候选人/简历不存在", candidate_id)
            return False
        job_id = resume.job_id
        prev_status = cand.status
        audit.info(
            "简历解析开始 candidate_id=%s job_id=%s preserve_status=%s",
            candidate_id, job_id, preserve_status,
        )

        # 该职位的要求项（含判定标准），作为匹配依据
        reqs = req_repo.list_by_job(job_id) if job_id else []
        # 职位未配置要求项：自动从 JD 提取并持久化，避免匹配建议为空
        if not reqs and job_id:
            reqs = _auto_generate_requirements(db, job_id, req_repo)
        req_payload, standard_ids = _enrich_requirements_with_standards(db, reqs)

        try:
            retrieval_token = set_retrieval_ids(standard_ids)
            try:
                result = json.loads(parse_resume(resume.resume_path, req_payload))
            finally:
                reset_retrieval_ids(retrieval_token)
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
            return False

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
        return True
    finally:
        reset_request_id(request_token)
        db.close()
        _release_parse(candidate_id, lock)
