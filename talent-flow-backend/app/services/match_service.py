from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Candidate, Job, Match
from ..schemas.match import MatchCreate, MatchOut, MatchUpdate


class MatchNotFoundError(Exception):
    pass


class MatchService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_by_candidate(self, candidate_id: int) -> list[MatchOut]:
        items = (
            self.db.execute(
                select(Match).where(Match.candidate_id == candidate_id).order_by(Match.id)
            )
            .scalars()
            .all()
        )
        return [MatchOut.model_validate(i) for i in items]

    def create(self, payload: MatchCreate) -> MatchOut:
        if not self.db.get(Job, payload.job_id):
            raise MatchNotFoundError(f"job {payload.job_id} not found")
        if not self.db.get(Candidate, payload.candidate_id):
            raise MatchNotFoundError(f"candidate {payload.candidate_id} not found")
        item = Match(**payload.model_dump())
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return MatchOut.model_validate(item)

    def update(self, item_id: int, payload: MatchUpdate) -> MatchOut:
        item = self.db.get(Match, item_id)
        if not item:
            raise MatchNotFoundError(f"match {item_id} not found")
        for k, v in payload.model_dump(exclude_unset=True).items():
            setattr(item, k, v)
        self.db.commit()
        self.db.refresh(item)
        return MatchOut.model_validate(item)

    def delete(self, item_id: int) -> None:
        item = self.db.get(Match, item_id)
        if not item:
            raise MatchNotFoundError(f"match {item_id} not found")
        self.db.delete(item)
        self.db.commit()
