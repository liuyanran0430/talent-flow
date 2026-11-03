from sqlalchemy.orm import Session

from ..models import Match
from ..repositories import CandidateRepository, JobRepository, MatchRepository
from ..schemas.match import MatchCreate, MatchOut, MatchUpdate


class MatchNotFoundError(Exception):
    pass


class MatchService:
    def __init__(self, db: Session) -> None:
        self.repo = MatchRepository(db)
        self.job_repo = JobRepository(db)
        self.candidate_repo = CandidateRepository(db)

    def list_by_candidate(self, candidate_id: int) -> list[MatchOut]:
        return [MatchOut.model_validate(i) for i in self.repo.list_by_candidate(candidate_id)]

    def create(self, payload: MatchCreate) -> MatchOut:
        if not self.job_repo.get(payload.job_id):
            raise MatchNotFoundError(f"job {payload.job_id} not found")
        if not self.candidate_repo.get(payload.candidate_id):
            raise MatchNotFoundError(f"candidate {payload.candidate_id} not found")
        item = Match(**payload.model_dump())
        self.repo.add(item)
        self.repo.commit()
        self.repo.refresh(item)
        return MatchOut.model_validate(item)

    def update(self, item_id: int, payload: MatchUpdate) -> MatchOut:
        item = self.repo.get(item_id)
        if not item:
            raise MatchNotFoundError(f"match {item_id} not found")
        for k, v in payload.model_dump(exclude_unset=True).items():
            setattr(item, k, v)
        self.repo.commit()
        self.repo.refresh(item)
        return MatchOut.model_validate(item)

    def delete(self, item_id: int) -> None:
        item = self.repo.get(item_id)
        if not item:
            raise MatchNotFoundError(f"match {item_id} not found")
        self.repo.delete(item)
        self.repo.commit()
