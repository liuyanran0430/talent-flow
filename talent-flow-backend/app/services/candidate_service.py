import os
from datetime import datetime

from sqlalchemy.orm import Session

from ..core.logging_config import get_logger
from ..models import Candidate, ResumeInfo
from ..repositories import CandidateRepository, JobFitRepository, ResumeRepository
from ..schemas.candidate import CandidateCreate, CandidateOut, CandidateUpdate

# 简历侧字段（物理上在 resume_infos 表）：更新时路由到 resume，而非 candidates
_RESUME_FIELDS = {"job_id", "experience", "info", "resume_path", "resume_hash", "analysis", "review_note"}

logger = get_logger("candidate_service")


class CandidateNotFoundError(Exception):
    pass


class CandidateService:
    def __init__(self, db: Session) -> None:
        self.repo = CandidateRepository(db)
        self.resume_repo = ResumeRepository(db)
        self.jobfit_repo = JobFitRepository(db)

    def _get_or_create_resume(self, c: Candidate) -> ResumeInfo:
        if c.resume is None:
            c.resume = ResumeInfo(candidate_id=c.id)
        return c.resume

    def list_candidates(
        self,
        *,
        search: str | None = None,
        status: str | None = None,
        job_id: int | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[CandidateOut], int]:
        items, total = self.repo.list(
            search=search, status=status, job_id=job_id, page=page, page_size=page_size
        )
        return [CandidateOut.model_validate(c) for c in items], total

    def get_candidate(self, candidate_id: int) -> CandidateOut:
        c = self.repo.get(candidate_id)
        if not c:
            raise CandidateNotFoundError(f"candidate {candidate_id} not found")
        return CandidateOut.model_validate(c)

    def create_candidate(self, payload: CandidateCreate) -> Candidate:
        data = payload.model_dump()
        resume_fields = {k: data.pop(k) for k in list(data.keys()) if k in _RESUME_FIELDS}
        c = Candidate(**data)
        # 只要带了任一简历侧字段，就同时建简历行（一对一）
        if any(v is not None for v in resume_fields.values()):
            c.resume = ResumeInfo(**resume_fields)
        self.repo.add(c)
        self.repo.commit()
        self.repo.refresh(c)
        return c

    def update_candidate(self, candidate_id: int, payload: CandidateUpdate) -> Candidate:
        c = self.repo.get(candidate_id)
        if not c:
            raise CandidateNotFoundError(f"candidate {candidate_id} not found")
        resume = None
        for k, v in payload.model_dump(exclude_unset=True).items():
            if k in _RESUME_FIELDS:
                resume = resume or self._get_or_create_resume(c)
                setattr(resume, k, v)
            else:
                setattr(c, k, v)
        self.repo.commit()
        self.repo.refresh(c)
        return c

    def delete_candidate(self, candidate_id: int) -> None:
        c = self.repo.get(candidate_id)
        if not c:
            raise CandidateNotFoundError(f"candidate {candidate_id} not found")
        # 级联清理匹配建议与简历文件（resume 行由 cascade 一并删除）
        self.jobfit_repo.delete_by_candidate(candidate_id)
        resume_path = c.resume.resume_path if c.resume else None
        self.repo.delete(c)
        self.repo.commit()
        if resume_path:
            try:
                os.remove(resume_path)
            except OSError:
                pass  # 文件不存在或无法删除时忽略，避免影响记录删除

    def find_by_resume_hash(self, resume_hash: str) -> ResumeInfo | None:
        """简历内容哈希查重，命中返回已存在的简历行（含 candidate_id / job_id）。"""
        return self.resume_repo.find_by_hash(resume_hash)

    def mark_parsing(self, candidate_id: int) -> tuple[Candidate, bool]:
        """标记候选人进入解析中，返回 (候选人, 是否放行)。

        僵死自愈：status=processing 且 3 分钟内未完成（服务重载/进程被杀导致后台任务丢失），
        放行重新触发；未超时不放行（already parsing）。
        """
        c = self.repo.get(candidate_id)
        if not c:
            raise CandidateNotFoundError(f"candidate {candidate_id} not found")
        if c.status == "processing":
            elapsed = (datetime.now() - c.updated_at).total_seconds()
            if elapsed < 180:
                return c, False
            logger.warning("僵死自愈放行重新解析 candidate_id=%s 卡顿时长=%.0fs", candidate_id, elapsed)
        c.status = "processing"
        if c.resume:
            c.resume.info = "正在解析简历"
        self.repo.commit()
        return c, True

    def stats_summary(self) -> dict:
        return {
            "total": self.repo.count_all(),
            "recommended": self.repo.count_by_statuses(["recommended"]),
            "active_7d": self.repo.count_active_7d(),
            "pending": self.repo.count_by_statuses(["review", "recommended"]),
        }
