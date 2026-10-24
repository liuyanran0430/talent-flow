from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Candidate, JobFit, RequirementItem
from ..schemas.jobfit import JobFitCreate, JobFitOut, JobFitUpdate


class JobFitNotFoundError(Exception):
    pass


class JobFitService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_by_candidate(self, candidate_id: int) -> list[JobFitOut]:
        items = (
            self.db.execute(
                select(JobFit).where(JobFit.candidate_id == candidate_id).order_by(JobFit.id)
            )
            .scalars()
            .all()
        )
        return [JobFitOut.model_validate(i) for i in items]

    def create(self, payload: JobFitCreate) -> JobFitOut:
        if not self.db.get(Candidate, payload.candidate_id):
            raise JobFitNotFoundError(f"candidate {payload.candidate_id} not found")
        if not self.db.get(RequirementItem, payload.requirement_item_id):
            raise JobFitNotFoundError(f"requirement item {payload.requirement_item_id} not found")
        item = JobFit(**payload.model_dump())
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return JobFitOut.model_validate(item)

    def update(self, item_id: int, payload: JobFitUpdate) -> JobFitOut:
        item = self.db.get(JobFit, item_id)
        if not item:
            raise JobFitNotFoundError(f"jobfit {item_id} not found")
        for k, v in payload.model_dump(exclude_unset=True).items():
            setattr(item, k, v)
        self.db.commit()
        self.db.refresh(item)
        return JobFitOut.model_validate(item)

    def delete(self, item_id: int) -> None:
        item = self.db.get(JobFit, item_id)
        if not item:
            raise JobFitNotFoundError(f"jobfit {item_id} not found")
        self.db.delete(item)
        self.db.commit()
