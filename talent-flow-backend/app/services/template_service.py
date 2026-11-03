from sqlalchemy.orm import Session

from ..models import RequirementItem, RequirementTemplate, TemplateItem
from ..repositories import JobRepository, RequirementRepository, TemplateRepository
from ..schemas.template import (
    RequirementTemplateCreate,
    RequirementTemplateOut,
    RequirementTemplateUpdate,
    TemplateItemCreate,
    TemplateItemOut,
    TemplateItemUpdate,
)


class TemplateNotFoundError(Exception):
    pass


class TemplateItemNotFoundError(Exception):
    pass


def _to_out(tpl: RequirementTemplate, items: list[TemplateItem]) -> RequirementTemplateOut:
    out = RequirementTemplateOut.model_validate(tpl)
    out.items = [TemplateItemOut.model_validate(i) for i in items]
    return out


class TemplateService:
    def __init__(self, db: Session) -> None:
        self.repo = TemplateRepository(db)
        self.job_repo = JobRepository(db)
        self.requirement_repo = RequirementRepository(db)

    def list_templates(self) -> list[RequirementTemplateOut]:
        return [_to_out(tpl, self.repo.items_of(tpl.id)) for tpl in self.repo.list_all()]

    def get(self, template_id: int) -> RequirementTemplateOut:
        tpl = self.repo.get(template_id)
        if not tpl:
            raise TemplateNotFoundError(f"template {template_id} not found")
        return _to_out(tpl, self.repo.items_of(tpl.id))

    def create(self, payload: RequirementTemplateCreate) -> RequirementTemplateOut:
        if self.repo.get_by_name(payload.name):
            raise ValueError(f"模板名称「{payload.name}」已存在")
        tpl = RequirementTemplate(name=payload.name, description=payload.description)
        self.repo.add(tpl)
        self.repo.flush()
        for it in payload.items:
            self.repo.add_item(
                TemplateItem(
                    template_id=tpl.id,
                    name=it.name,
                    type=it.type,
                    importance=it.importance,
                    standard=it.standard,
                )
            )
        self.repo.commit()
        self.repo.refresh(tpl)
        return _to_out(tpl, self.repo.items_of(tpl.id))

    def update(self, template_id: int, payload: RequirementTemplateUpdate) -> RequirementTemplateOut:
        tpl = self.repo.get(template_id)
        if not tpl:
            raise TemplateNotFoundError(f"template {template_id} not found")
        for k, v in payload.model_dump(exclude_unset=True).items():
            setattr(tpl, k, v)
        self.repo.commit()
        self.repo.refresh(tpl)
        return _to_out(tpl, self.repo.items_of(tpl.id))

    def delete(self, template_id: int) -> None:
        tpl = self.repo.get(template_id)
        if not tpl:
            raise TemplateNotFoundError(f"template {template_id} not found")
        self.repo.delete(tpl)
        self.repo.commit()

    def add_item(self, template_id: int, payload: TemplateItemCreate) -> TemplateItemOut:
        if not self.repo.get(template_id):
            raise TemplateNotFoundError(f"template {template_id} not found")
        it = TemplateItem(template_id=template_id, **payload.model_dump())
        self.repo.add_item(it)
        self.repo.commit()
        self.repo.refresh(it)
        return TemplateItemOut.model_validate(it)

    def update_item(self, item_id: int, payload: TemplateItemUpdate) -> TemplateItemOut:
        it = self.repo.get_item(item_id)
        if not it:
            raise TemplateItemNotFoundError(f"template item {item_id} not found")
        for k, v in payload.model_dump(exclude_unset=True).items():
            setattr(it, k, v)
        self.repo.commit()
        self.repo.refresh(it)
        return TemplateItemOut.model_validate(it)

    def delete_item(self, item_id: int) -> None:
        it = self.repo.get_item(item_id)
        if not it:
            raise TemplateItemNotFoundError(f"template item {item_id} not found")
        self.repo.delete_item(it)
        self.repo.commit()

    def apply(self, template_id: int, job_id: int) -> dict:
        tpl = self.repo.get(template_id)
        if not tpl:
            raise TemplateNotFoundError(f"template {template_id} not found")
        if not self.job_repo.get(job_id):
            raise TemplateNotFoundError(f"job {job_id} not found")
        items = self.repo.items_of(template_id)
        for it in items:
            self.requirement_repo.add(
                RequirementItem(
                    job_id=job_id,
                    name=it.name,
                    type=it.type,
                    importance=it.importance,
                    standard=it.standard,
                )
            )
        tpl.usage_count = (tpl.usage_count or 0) + 1
        self.repo.commit()
        return {"applied": len(items), "usage_count": tpl.usage_count}
