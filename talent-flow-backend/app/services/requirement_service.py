from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Job, JobFit, RequirementItem
from ..schemas.requirement import (
    RequirementItemCreate,
    RequirementItemOut,
    RequirementItemUpdate,
)


class RequirementNotFoundError(Exception):
    pass


class RequirementService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_by_job(self, job_id: int) -> list[RequirementItemOut]:
        items = (
            self.db.execute(
                select(RequirementItem)
                .where(RequirementItem.job_id == job_id)
                .order_by(RequirementItem.id)
            )
            .scalars()
            .all()
        )
        return [RequirementItemOut.model_validate(i) for i in items]

    def create(self, payload: RequirementItemCreate) -> RequirementItemOut:
        if not self.db.get(Job, payload.job_id):
            raise RequirementNotFoundError(f"job {payload.job_id} not found")
        item = RequirementItem(**payload.model_dump())
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return RequirementItemOut.model_validate(item)

    def update(self, item_id: int, payload: RequirementItemUpdate) -> RequirementItemOut:
        item = self.db.get(RequirementItem, item_id)
        if not item:
            raise RequirementNotFoundError(f"requirement item {item_id} not found")
        for k, v in payload.model_dump(exclude_unset=True).items():
            setattr(item, k, v)
        self.db.commit()
        self.db.refresh(item)
        return RequirementItemOut.model_validate(item)

    def delete(self, item_id: int) -> None:
        item = self.db.get(RequirementItem, item_id)
        if not item:
            raise RequirementNotFoundError(f"requirement item {item_id} not found")
        # 级联清理关联的匹配建议，避免悬挂记录
        self.db.query(JobFit).filter(JobFit.requirement_item_id == item_id).delete()
        self.db.delete(item)
        self.db.commit()
