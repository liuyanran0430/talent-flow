from sqlalchemy import select

from ..models import RequirementTemplate, TemplateItem
from .base import BaseRepository


class TemplateRepository(BaseRepository):
    """requirement_templates / template_items 表读写入口。"""

    def list_all(self) -> list[RequirementTemplate]:
        return list(
            self.db.execute(select(RequirementTemplate).order_by(RequirementTemplate.created_at.desc()))
            .scalars()
            .all()
        )

    def get(self, template_id: int) -> RequirementTemplate | None:
        return self.db.get(RequirementTemplate, template_id)

    def get_by_name(self, name: str) -> RequirementTemplate | None:
        return self.db.execute(
            select(RequirementTemplate).where(RequirementTemplate.name == name)
        ).scalar_one_or_none()

    def add(self, tpl: RequirementTemplate) -> None:
        self.db.add(tpl)

    def delete(self, tpl: RequirementTemplate) -> None:
        self.db.delete(tpl)

    def items_of(self, template_id: int) -> list[TemplateItem]:
        return list(
            self.db.execute(
                select(TemplateItem).where(TemplateItem.template_id == template_id).order_by(TemplateItem.id)
            )
            .scalars()
            .all()
        )

    def get_item(self, item_id: int) -> TemplateItem | None:
        return self.db.get(TemplateItem, item_id)

    def add_item(self, item: TemplateItem) -> None:
        self.db.add(item)

    def delete_item(self, item: TemplateItem) -> None:
        self.db.delete(item)
