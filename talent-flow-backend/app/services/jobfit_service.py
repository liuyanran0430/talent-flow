from sqlalchemy.orm import Session

from ..models import JobFit
from ..repositories import CandidateRepository, JobFitRepository, RequirementRepository
from ..schemas.jobfit import JobFitCreate, JobFitOut, JobFitUpdate


class JobFitNotFoundError(Exception):
    pass


class JobFitService:
    def __init__(self, db: Session) -> None:
        self.repo = JobFitRepository(db)
        self.candidate_repo = CandidateRepository(db)
        self.requirement_repo = RequirementRepository(db)

    def list_by_candidate(self, candidate_id: int) -> list[JobFitOut]:
        return [JobFitOut.model_validate(i) for i in self.repo.list_by_candidate(candidate_id)]

    def create(self, payload: JobFitCreate) -> JobFitOut:
        if not self.candidate_repo.get(payload.candidate_id):
            raise JobFitNotFoundError(f"candidate {payload.candidate_id} not found")
        if not self.requirement_repo.get(payload.requirement_item_id):
            raise JobFitNotFoundError(f"requirement item {payload.requirement_item_id} not found")
        item = JobFit(**payload.model_dump())
        self.repo.add(item)
        self.repo.commit()
        self.repo.refresh(item)
        return JobFitOut.model_validate(item)

    def update(self, item_id: int, payload: JobFitUpdate) -> JobFitOut:
        item = self.repo.get(item_id)
        if not item:
            raise JobFitNotFoundError(f"jobfit {item_id} not found")
        for k, v in payload.model_dump(exclude_unset=True).items():
            setattr(item, k, v)
        self.repo.commit()
        self.repo.refresh(item)
        return JobFitOut.model_validate(item)

    def delete(self, item_id: int) -> None:
        item = self.repo.get(item_id)
        if not item:
            raise JobFitNotFoundError(f"jobfit {item_id} not found")
        self.repo.delete(item)
        self.repo.commit()
