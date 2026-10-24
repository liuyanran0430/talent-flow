from sqlalchemy import Integer, cast, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..models import Candidate, Job, RequirementItem
from ..schemas.job import JobCreate, JobStatus, JobUpdate, JobWithStats, STATUS_LABEL_MAP


class JobNotFoundError(Exception):
    pass


class JobService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_jobs(
        self,
        *,
        search: str | None = None,
        status: str | None = None,
    ) -> list[JobWithStats]:
        stmt = select(Job).options(selectinload(Job.department)).order_by(Job.created_at.desc())
        if search:
            like = f"%{search}%"
            stmt = stmt.where(Job.name.like(like))
        if status and status != "all":
            stmt = stmt.where(Job.status == status)

        jobs = self.db.execute(stmt).scalars().all()
        stats = self._batch_stats([j.id for j in jobs])
        result: list[JobWithStats] = []
        for j in jobs:
            hired, candidates = stats.get(j.id, (0, 0))
            progress = int(hired / j.headcount * 100) if j.headcount else 0
            item = JobWithStats.model_validate(j)
            item.status_label = STATUS_LABEL_MAP.get(JobStatus(j.status), j.status)
            item.dept_label = j.department.name if j.department else None
            item.hired = hired
            item.candidates = candidates
            item.progress = min(progress, 100)
            result.append(item)
        return result

    def get_job(self, job_id: int) -> JobWithStats:
        stmt = select(Job).options(selectinload(Job.department)).where(Job.id == job_id)
        job = self.db.execute(stmt).scalar_one_or_none()
        if not job:
            raise JobNotFoundError(f"job {job_id} not found")
        hired, candidates = self._stats_for(job_id)
        progress = int(hired / job.headcount * 100) if job.headcount else 0
        item = JobWithStats.model_validate(job)
        item.status_label = STATUS_LABEL_MAP.get(JobStatus(job.status), job.status)
        item.dept_label = job.department.name if job.department else None
        item.hired = hired
        item.candidates = candidates
        item.progress = min(progress, 100)
        return item

    def create_job(self, payload: JobCreate) -> Job:
        data = payload.model_dump()
        if data.get("description"):
            data["description"] = data["description"].strip()
        job = Job(**data)
        self.db.add(job)
        try:
            self.db.commit()
        except IntegrityError as e:
            self.db.rollback()
            raise e
        self.db.refresh(job)
        return job

    def update_job(self, job_id: int, payload: JobUpdate) -> Job:
        job = self.db.get(Job, job_id)
        if not job:
            raise JobNotFoundError(f"job {job_id} not found")
        data = payload.model_dump(exclude_unset=True)
        if data.get("description"):
            data["description"] = data["description"].strip()
        for k, v in data.items():
            setattr(job, k, v)
        self.db.commit()
        self.db.refresh(job)
        return job

    def delete_job(self, job_id: int) -> None:
        job = self.db.get(Job, job_id)
        if not job:
            raise JobNotFoundError(f"job {job_id} not found")
        self.db.delete(job)
        self.db.commit()

    def _stats_for(self, job_id: int) -> tuple[int, int]:
        stats = self._batch_stats([job_id])
        return stats.get(job_id, (0, 0))

    def _batch_stats(self, job_ids: list[int]) -> dict[int, tuple[int, int]]:
        """批量返回 {job_id: (已入职数, 候选人总数)}"""
        if not job_ids:
            return {}
        stmt = (
            select(
                Candidate.job_id,
                func.count().label("total"),
                func.sum(cast(Candidate.status == "hired", Integer)).label("hired"),
            )
            .where(Candidate.job_id.in_(job_ids))
            .group_by(Candidate.job_id)
        )
        rows = self.db.execute(stmt).all()
        return {row.job_id: (int(row.hired or 0), int(row.total or 0)) for row in rows}

    def stats_summary(self) -> dict:
        """招聘总览统计"""
        total = self.db.scalar(select(func.count()).select_from(Job)) or 0
        open_count = self.db.scalar(select(func.count()).select_from(Job).where(Job.status == JobStatus.open.value)) or 0
        urgent = self.db.scalar(select(func.count()).select_from(Job).where(Job.status == JobStatus.urgent.value)) or 0
        paused = self.db.scalar(select(func.count()).select_from(Job).where(Job.status == JobStatus.paused.value)) or 0
        no_requirement = self.db.scalar(
            select(func.count())
            .select_from(Job)
            .where(~Job.id.in_(select(RequirementItem.job_id)))
        ) or 0
        hired_total = self.db.scalar(
            select(func.count()).select_from(Candidate).where(Candidate.status == "hired")
        ) or 0
        return {
            "total_jobs": int(total),
            "open_jobs": int(open_count),
            "urgent_jobs": int(urgent),
            "paused_jobs": int(paused),
            "no_requirement_jobs": int(no_requirement),
            "hired_total": int(hired_total),
        }
