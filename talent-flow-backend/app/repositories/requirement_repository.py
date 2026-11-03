from sqlalchemy import select

from ..models import JobFit, RequirementItem
from .base import BaseRepository


class RequirementRepository(BaseRepository):
    """requirement_items 表读写入口（含按职位整体覆盖的批量写入）。"""

    def list_by_job(self, job_id: int) -> list[RequirementItem]:
        return list(
            self.db.execute(
                select(RequirementItem).where(RequirementItem.job_id == job_id).order_by(RequirementItem.id)
            )
            .scalars()
            .all()
        )

    def get(self, item_id: int) -> RequirementItem | None:
        return self.db.get(RequirementItem, item_id)

    def add(self, item: RequirementItem) -> None:
        self.db.add(item)

    def delete(self, item: RequirementItem) -> None:
        self.db.delete(item)

    def delete_by_job(self, job_id: int) -> int:
        return self.db.query(RequirementItem).filter(RequirementItem.job_id == job_id).delete()

    def bulk_create(self, job_id: int, items: list[dict]) -> list[RequirementItem]:
        """批量插入要求项（每条 flush 拿 id），与 delete_by_job 组合实现整体覆盖；不 commit。"""
        created: list[RequirementItem] = []
        for data in items:
            item = RequirementItem(job_id=job_id, **data)
            self.db.add(item)
            self.db.flush()
            created.append(item)
        return created

    def delete_jobfits_by_item(self, item_id: int) -> int:
        """级联清理某要求项关联的匹配建议，避免悬挂记录。"""
        return self.db.query(JobFit).filter(JobFit.requirement_item_id == item_id).delete()
