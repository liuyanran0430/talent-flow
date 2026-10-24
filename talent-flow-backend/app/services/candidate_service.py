from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

import os

from ..models import Candidate
from ..models.jobfit import JobFit
from ..schemas.candidate import CandidateCreate, CandidateOut, CandidateUpdate


class CandidateNotFoundError(Exception):
    pass


class CandidateService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_candidates(
        self,
        *,
        search: str | None = None,
        status: str | None = None,
        job_id: int | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[CandidateOut], int]:
        stmt = select(Candidate).order_by(Candidate.created_at.desc())
        if search:
            like = f"%{search}%"
            stmt = stmt.where(Candidate.name.like(like))
        if status and status != "all":
            stmt = stmt.where(Candidate.status == status)
        if job_id:
            stmt = stmt.where(Candidate.job_id == job_id)

        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        items = self.db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars().all()
        return [CandidateOut.model_validate(c) for c in items], int(total)

    def get_candidate(self, candidate_id: int) -> CandidateOut:
        c = self.db.get(Candidate, candidate_id)
        if not c:
            raise CandidateNotFoundError(f"candidate {candidate_id} not found")
        return CandidateOut.model_validate(c)

    def create_candidate(self, payload: CandidateCreate) -> Candidate:
        c = Candidate(**payload.model_dump())
        self.db.add(c)
        self.db.commit()
        self.db.refresh(c)
        return c

    def update_candidate(self, candidate_id: int, payload: CandidateUpdate) -> Candidate:
        c = self.db.get(Candidate, candidate_id)
        if not c:
            raise CandidateNotFoundError(f"candidate {candidate_id} not found")
        for k, v in payload.model_dump(exclude_unset=True).items():
            setattr(c, k, v)
        self.db.commit()
        self.db.refresh(c)
        return c

    def delete_candidate(self, candidate_id: int) -> None:
        c = self.db.get(Candidate, candidate_id)
        if not c:
            raise CandidateNotFoundError(f"candidate {candidate_id} not found")
        # 级联清理匹配建议与简历文件
        self.db.query(JobFit).filter(JobFit.candidate_id == candidate_id).delete()
        resume_path = c.resume_path
        self.db.delete(c)
        self.db.commit()
        if resume_path:
            try:
                os.remove(resume_path)
            except OSError:
                pass  # 文件不存在或无法删除时忽略，避免影响记录删除

    def stats_summary(self) -> dict:
        total = self.db.scalar(select(func.count()).select_from(Candidate)) or 0
        recommended = self.db.scalar(
            select(func.count()).select_from(Candidate).where(Candidate.status == "recommended")
        ) or 0
        active_7d = self.db.scalar(
            select(func.count())
            .select_from(Candidate)
            .where(Candidate.updated_at >= func.date_sub(func.now(), text("7 DAY")))
        ) or 0
        pending = self.db.scalar(
            select(func.count()).select_from(Candidate).where(Candidate.status.in_(["review", "recommended"]))
        ) or 0
        return {
            "total": int(total),
            "recommended": int(recommended),
            "active_7d": int(active_7d),
            "pending": int(pending),
        }
