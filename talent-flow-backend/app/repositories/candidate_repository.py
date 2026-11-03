from __future__ import annotations

from sqlalchemy import func, select, text
from sqlalchemy.orm import joinedload

from ..models import Candidate, ResumeInfo
from .base import BaseRepository


class CandidateRepository(BaseRepository):
    """candidates 表（含一对一 resume_infos 关联查询）读写入口。"""

    def get(self, candidate_id: int) -> Candidate | None:
        return self.db.get(Candidate, candidate_id)

    def list(
        self,
        *,
        search: str | None = None,
        status: str | None = None,
        job_id: int | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Candidate], int]:
        stmt = select(Candidate).options(joinedload(Candidate.resume)).order_by(Candidate.created_at.desc())
        if search:
            stmt = stmt.where(Candidate.name.like(f"%{search}%"))
        if status and status != "all":
            stmt = stmt.where(Candidate.status == status)
        if job_id:
            # job_id 已迁移到简历表，需 join 过滤
            stmt = stmt.join(ResumeInfo, ResumeInfo.candidate_id == Candidate.id).where(ResumeInfo.job_id == job_id)

        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        items = self.db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).unique().scalars().all()
        return list(items), int(total)

    def add(self, candidate: Candidate) -> None:
        self.db.add(candidate)

    def delete(self, candidate: Candidate) -> None:
        self.db.delete(candidate)

    def find_by_resume_hash(self, resume_hash: str) -> ResumeInfo | None:
        return self.db.query(ResumeInfo).filter(ResumeInfo.resume_hash == resume_hash).first()

    def list_parsed_by_job(self, job_id: int, statuses: tuple[str, ...] = ("review", "finish")) -> list[Candidate]:
        """某职位下已进入解析流程（review/finish）的候选人，供要求变化重算使用。"""
        return (
            self.db.query(Candidate)
            .join(ResumeInfo, ResumeInfo.candidate_id == Candidate.id)
            .filter(ResumeInfo.job_id == job_id, Candidate.status.in_(statuses))
            .all()
        )

    def count_recalculable(self, job_id: int, statuses: tuple[str, ...] = ("review", "finish")) -> int:
        """某职位下可重算（已解析且简历文件存在）的候选人数。"""
        return (
            self.db.query(Candidate)
            .join(ResumeInfo, ResumeInfo.candidate_id == Candidate.id)
            .filter(
                ResumeInfo.job_id == job_id,
                Candidate.status.in_(statuses),
                ResumeInfo.resume_path.isnot(None),
            )
            .count()
        )

    # ---- 统计（stats_summary 用；含 MySQL 方言 date_sub，测试环境不覆盖该方法） ----
    def count_all(self) -> int:
        return int(self.db.scalar(select(func.count()).select_from(Candidate)) or 0)

    def count_by_statuses(self, statuses: list[str]) -> int:
        return int(
            self.db.scalar(select(func.count()).select_from(Candidate).where(Candidate.status.in_(statuses))) or 0
        )

    def count_active_7d(self) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(Candidate)
                .where(Candidate.updated_at >= func.date_sub(func.now(), text("7 DAY")))
            ) or 0
        )
