from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Job, RequirementItem, RequirementTemplate, TemplateItem
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
        self.db = db

    def list_templates(self) -> list[RequirementTemplateOut]:
        tpls = (
            self.db.execute(
                select(RequirementTemplate).order_by(RequirementTemplate.created_at.desc())
            )
            .scalars()
            .all()
        )
        return [_to_out(tpl, self._items_of(tpl.id)) for tpl in tpls]

    def get(self, template_id: int) -> RequirementTemplateOut:
        tpl = self.db.get(RequirementTemplate, template_id)
        if not tpl:
            raise TemplateNotFoundError(f"template {template_id} not found")
        return _to_out(tpl, self._items_of(tpl.id))

    def create(self, payload: RequirementTemplateCreate) -> RequirementTemplateOut:
        existing = self.db.execute(
            select(RequirementTemplate).where(RequirementTemplate.name == payload.name)
        ).scalar_one_or_none()
        if existing:
            raise ValueError(f"模板名称「{payload.name}」已存在")
        tpl = RequirementTemplate(name=payload.name, description=payload.description)
        self.db.add(tpl)
        self.db.flush()
        for it in payload.items:
            self.db.add(
                TemplateItem(
                    template_id=tpl.id,
                    name=it.name,
                    type=it.type,
                    importance=it.importance,
                    standard=it.standard,
                )
            )
        self.db.commit()
        self.db.refresh(tpl)
        return _to_out(tpl, self._items_of(tpl.id))

    def update(self, template_id: int, payload: RequirementTemplateUpdate) -> RequirementTemplateOut:
        tpl = self.db.get(RequirementTemplate, template_id)
        if not tpl:
            raise TemplateNotFoundError(f"template {template_id} not found")
        for k, v in payload.model_dump(exclude_unset=True).items():
            setattr(tpl, k, v)
        self.db.commit()
        self.db.refresh(tpl)
        return _to_out(tpl, self._items_of(tpl.id))

    def delete(self, template_id: int) -> None:
        tpl = self.db.get(RequirementTemplate, template_id)
        if not tpl:
            raise TemplateNotFoundError(f"template {template_id} not found")
        self.db.delete(tpl)
        self.db.commit()

    def add_item(self, template_id: int, payload: TemplateItemCreate) -> TemplateItemOut:
        if not self.db.get(RequirementTemplate, template_id):
            raise TemplateNotFoundError(f"template {template_id} not found")
        it = TemplateItem(template_id=template_id, **payload.model_dump())
        self.db.add(it)
        self.db.commit()
        self.db.refresh(it)
        return TemplateItemOut.model_validate(it)

    def update_item(self, item_id: int, payload: TemplateItemUpdate) -> TemplateItemOut:
        it = self.db.get(TemplateItem, item_id)
        if not it:
            raise TemplateItemNotFoundError(f"template item {item_id} not found")
        for k, v in payload.model_dump(exclude_unset=True).items():
            setattr(it, k, v)
        self.db.commit()
        self.db.refresh(it)
        return TemplateItemOut.model_validate(it)

    def delete_item(self, item_id: int) -> None:
        it = self.db.get(TemplateItem, item_id)
        if not it:
            raise TemplateItemNotFoundError(f"template item {item_id} not found")
        self.db.delete(it)
        self.db.commit()

    def apply(self, template_id: int, job_id: int) -> dict:
        tpl = self.db.get(RequirementTemplate, template_id)
        if not tpl:
            raise TemplateNotFoundError(f"template {template_id} not found")
        if not self.db.get(Job, job_id):
            raise TemplateNotFoundError(f"job {job_id} not found")
        items = self._items_of(template_id)
        for it in items:
            self.db.add(
                RequirementItem(
                    job_id=job_id,
                    name=it.name,
                    type=it.type,
                    importance=it.importance,
                    standard=it.standard,
                )
            )
        tpl.usage_count = (tpl.usage_count or 0) + 1
        self.db.commit()
        return {"applied": len(items), "usage_count": tpl.usage_count}

    def _items_of(self, template_id: int) -> list[TemplateItem]:
        return list(
            self.db.execute(
                select(TemplateItem)
                .where(TemplateItem.template_id == template_id)
                .order_by(TemplateItem.id)
            )
            .scalars()
            .all()
        )
