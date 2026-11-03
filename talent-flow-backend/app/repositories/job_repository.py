from __future__ import annotations

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.orm import selectinload

from ..models import Candidate, Job, RequirementItem, ResumeInfo
from .base import BaseRepository


class JobRepository(BaseRepository):
    """jobs 表读写入口（含职位-候选人统计聚合）。"""

    def get(self, job_id: int) -> Job | None:
        return self.db.get(Job, job_id)

    def get_with_department(self, job_id: int) -> Job | None:
        stmt = select(Job).options(selectinload(Job.department)).where(Job.id == job_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def list(self, *, search: str | None = None, status: str | None = None) -> list[Job]:
        stmt = select(Job).options(selectinload(Job.department)).order_by(Job.created_at.desc())
        if search:
            stmt = stmt.where(Job.name.like(f"%{search}%"))
        if status and status != "all":
            stmt = stmt.where(Job.status == status)
        return list(self.db.execute(stmt).scalars().all())

    def add(self, job: Job) -> None:
        self.db.add(job)

    def delete(self, job: Job) -> None:
        self.db.delete(job)

    def batch_candidate_stats(self, job_ids: list[int]) -> dict[int, tuple[int, int]]:
        """批量返回 {job_id: (已入职数, 候选人总数)}"""
        if not job_ids:
            return {}
        stmt = (
            select(
                ResumeInfo.job_id,
                func.count().label("total"),
                func.sum(cast(Candidate.status == "hired", Integer)).label("hired"),
            )
            .join(Candidate, Candidate.id == ResumeInfo.candidate_id)
            .where(ResumeInfo.job_id.in_(job_ids))
            .group_by(ResumeInfo.job_id)
        )
        rows = self.db.execute(stmt).all()
        return {row.job_id: (int(row.hired or 0), int(row.total or 0)) for row in rows}

    # ---- 招聘总览统计（stats_summary 用） ----
    def count_all(self) -> int:
        return int(self.db.scalar(select(func.count()).select_from(Job)) or 0)

    def count_by_status(self, status: str) -> int:
        return int(self.db.scalar(select(func.count()).select_from(Job).where(Job.status == status)) or 0)

    def count_without_requirement(self) -> int:
        return int(
            self.db.scalar(
                select(func.count()).select_from(Job).where(~Job.id.in_(select(RequirementItem.job_id)))
            ) or 0
        )

    def count_hired_candidates(self) -> int:
        return int(
            self.db.scalar(select(func.count()).select_from(Candidate).where(Candidate.status == "hired")) or 0
        )
