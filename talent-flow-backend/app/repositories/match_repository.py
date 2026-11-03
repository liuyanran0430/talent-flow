from sqlalchemy import select

from ..models import Match
from .base import BaseRepository


class MatchRepository(BaseRepository):
    """matches 表（岗位匹配打分）读写入口。"""

    def list_by_candidate(self, candidate_id: int) -> list[Match]:
        return list(
            self.db.execute(select(Match).where(Match.candidate_id == candidate_id).order_by(Match.id))
            .scalars()
            .all()
        )

    def get(self, item_id: int) -> Match | None:
        return self.db.get(Match, item_id)

    def get_by_candidate_job(self, candidate_id: int, job_id: int) -> Match | None:
        return (
            self.db.query(Match)
            .filter(Match.candidate_id == candidate_id, Match.job_id == job_id)
            .first()
        )

    def add(self, match: Match) -> None:
        self.db.add(match)

    def delete(self, match: Match) -> None:
        self.db.delete(match)
