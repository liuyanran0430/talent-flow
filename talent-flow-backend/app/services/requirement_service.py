import json

from sqlalchemy.orm import Session

from ..repositories import JobRepository, RequirementRepository
from ..schemas.requirement import (
    RequirementItemCreate,
    RequirementItemGen,
    RequirementItemOut,
    RequirementItemUpdate,
)
from .jd_parser import parse_jd


class RequirementNotFoundError(Exception):
    pass


class RequirementJdEmptyError(Exception):
    """职位未填写 JD，无法生成要求项"""

    pass


class RequirementGenerateEmptyError(Exception):
    """LLM 生成结果为空"""

    pass


class RequirementService:
    def __init__(self, db: Session) -> None:
        self.repo = RequirementRepository(db)
        self.job_repo = JobRepository(db)

    def list_by_job(self, job_id: int) -> list[RequirementItemOut]:
        return [RequirementItemOut.model_validate(i) for i in self.repo.list_by_job(job_id)]

    def ensure_job_exists(self, job_id: int) -> None:
        """职位存在性校验，不存在抛 RequirementNotFoundError。"""
        if not self.job_repo.get(job_id):
            raise RequirementNotFoundError(f"job {job_id} not found")

    def generate_from_jd(self, job_id: int) -> list[RequirementItemGen]:
        """基于职位 JD 调用 LLM 生成要求项（仅预览，不落库）。"""
        job = self.job_repo.get(job_id)
        if not job:
            raise RequirementNotFoundError(f"job {job_id} not found")
        if not job.description or not job.description.strip():
            raise RequirementJdEmptyError(f"job {job_id} has no JD")
        data = json.loads(parse_jd(job.description))
        items = [RequirementItemGen(**it) for it in data.get("items", [])]
        if not items:
            raise RequirementGenerateEmptyError(f"job {job_id} generated no items")
        return items

    def batch_replace(self, job_id: int, items: list[RequirementItemCreate]) -> list[RequirementItemOut]:
        """整体覆盖某职位的要求项：先删后插，同事务。"""
        if not self.job_repo.get(job_id):
            raise RequirementNotFoundError(f"job {job_id} not found")
        self.repo.delete_by_job(job_id)
        created = self.repo.bulk_create(
            job_id,
            [
                {"name": it.name.strip(), "type": it.type, "importance": it.importance, "standard": it.standard}
                for it in items
            ],
        )
        self.repo.commit()
        return [RequirementItemOut.model_validate(i) for i in created]

    def create(self, payload: RequirementItemCreate) -> RequirementItemOut:
        if not self.job_repo.get(payload.job_id):
            raise RequirementNotFoundError(f"job {payload.job_id} not found")
        from ..models import RequirementItem

        item = RequirementItem(**payload.model_dump())
        self.repo.add(item)
        self.repo.commit()
        self.repo.refresh(item)
        return RequirementItemOut.model_validate(item)

    def update(self, item_id: int, payload: RequirementItemUpdate) -> RequirementItemOut:
        item = self.repo.get(item_id)
        if not item:
            raise RequirementNotFoundError(f"requirement item {item_id} not found")
        for k, v in payload.model_dump(exclude_unset=True).items():
            setattr(item, k, v)
        self.repo.commit()
        self.repo.refresh(item)
        return RequirementItemOut.model_validate(item)

    def delete(self, item_id: int) -> None:
        item = self.repo.get(item_id)
        if not item:
            raise RequirementNotFoundError(f"requirement item {item_id} not found")
        # 级联清理关联的匹配建议，避免悬挂记录
        self.repo.delete_jobfits_by_item(item_id)
        self.repo.delete(item)
        self.repo.commit()
