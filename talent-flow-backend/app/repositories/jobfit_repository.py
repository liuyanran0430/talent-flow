from sqlalchemy import select

from ..models import JobFit
from .base import BaseRepository


class JobFitRepository(BaseRepository):
    """jobfits 表（职位匹配建议）读写入口。"""

    def list_by_candidate(self, candidate_id: int) -> list[JobFit]:
        return list(
            self.db.execute(select(JobFit).where(JobFit.candidate_id == candidate_id).order_by(JobFit.id))
            .scalars()
            .all()
        )

    def get(self, item_id: int) -> JobFit | None:
        return self.db.get(JobFit, item_id)

    def add(self, fit: JobFit) -> None:
        self.db.add(fit)

    def delete(self, fit: JobFit) -> None:
        self.db.delete(fit)

    def delete_by_candidate(self, candidate_id: int) -> int:
        """覆盖式重建前清空候选人全部匹配建议。"""
        return self.db.query(JobFit).filter(JobFit.candidate_id == candidate_id).delete()
