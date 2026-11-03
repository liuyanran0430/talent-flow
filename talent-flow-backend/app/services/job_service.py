from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Job
from ..repositories import JobRepository
from ..schemas.job import JobCreate, JobStatus, JobUpdate, JobWithStats, STATUS_LABEL_MAP


class JobNotFoundError(Exception):
    pass


class JobService:
    def __init__(self, db: Session) -> None:
        self.repo = JobRepository(db)

    def list_jobs(
        self,
        *,
        search: str | None = None,
        status: str | None = None,
    ) -> list[JobWithStats]:
        jobs = self.repo.list(search=search, status=status)
        stats = self.repo.batch_candidate_stats([j.id for j in jobs])
        return [self._to_out(j, *stats.get(j.id, (0, 0))) for j in jobs]

    def get_job(self, job_id: int) -> JobWithStats:
        job = self.repo.get_with_department(job_id)
        if not job:
            raise JobNotFoundError(f"job {job_id} not found")
        hired, candidates = self.repo.batch_candidate_stats([job_id]).get(job_id, (0, 0))
        return self._to_out(job, hired, candidates)

    def create_job(self, payload: JobCreate) -> Job:
        data = payload.model_dump()
        if data.get("description"):
            data["description"] = data["description"].strip()
        job = Job(**data)
        self.repo.add(job)
        try:
            self.repo.commit()
        except IntegrityError as e:
            self.repo.rollback()
            raise e
        self.repo.refresh(job)
        return job

    def update_job(self, job_id: int, payload: JobUpdate) -> Job:
        job = self.repo.get(job_id)
        if not job:
            raise JobNotFoundError(f"job {job_id} not found")
        data = payload.model_dump(exclude_unset=True)
        if data.get("description"):
            data["description"] = data["description"].strip()
        for k, v in data.items():
            setattr(job, k, v)
        self.repo.commit()
        self.repo.refresh(job)
        return job

    def delete_job(self, job_id: int) -> None:
        job = self.repo.get(job_id)
        if not job:
            raise JobNotFoundError(f"job {job_id} not found")
        self.repo.delete(job)
        self.repo.commit()

    def _to_out(self, job: Job, hired: int, candidates: int) -> JobWithStats:
        progress = int(hired / job.headcount * 100) if job.headcount else 0
        item = JobWithStats.model_validate(job)
        item.status_label = STATUS_LABEL_MAP.get(JobStatus(job.status), job.status)
        item.dept_label = job.department.name if job.department else None
        item.hired = hired
        item.candidates = candidates
        item.progress = min(progress, 100)
        return item

    def stats_summary(self) -> dict:
        """招聘总览统计"""
        return {
            "total_jobs": self.repo.count_all(),
            "open_jobs": self.repo.count_by_status(JobStatus.open.value),
            "urgent_jobs": self.repo.count_by_status(JobStatus.urgent.value),
            "paused_jobs": self.repo.count_by_status(JobStatus.paused.value),
            "no_requirement_jobs": self.repo.count_without_requirement(),
            "hired_total": self.repo.count_hired_candidates(),
        }
