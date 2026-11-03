from ..models import ResumeInfo
from .base import BaseRepository


class ResumeRepository(BaseRepository):
    """resume_infos 表读写入口。候选人一对一简历行通常经 Candidate.resume 访问，此处放独立查询。"""

    def find_by_hash(self, resume_hash: str) -> ResumeInfo | None:
        return self.db.query(ResumeInfo).filter(ResumeInfo.resume_hash == resume_hash).first()

    def get_by_candidate(self, candidate_id: int) -> ResumeInfo | None:
        return self.db.query(ResumeInfo).filter(ResumeInfo.candidate_id == candidate_id).first()
