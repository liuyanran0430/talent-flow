from sqlalchemy import select

from ..models import KbStandard, RequirementItem
from .base import BaseRepository


class KbStandardRepository(BaseRepository):
    """kb_standards 表读写入口。"""

    def list_by_filters(
        self,
        query: str | None = None,
        category: str | None = None,
        status: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[KbStandard]:
        stmt = select(KbStandard)
        if query:
            like = f"%{query.strip()}%"
            stmt = stmt.where(
                (KbStandard.name.like(like))
                | (KbStandard.code.like(like))
                | (KbStandard.aliases.like(like))
                | (KbStandard.standard.like(like))
            )
        if category:
            stmt = stmt.where(KbStandard.category == category)
        if status:
            stmt = stmt.where(KbStandard.status == status)
        stmt = stmt.order_by(KbStandard.updated_at.desc(), KbStandard.id.desc()).limit(limit).offset(offset)
        return list(self.db.execute(stmt).scalars().all())

    def list_published(self) -> list[KbStandard]:
        return list(
            self.db.execute(
                select(KbStandard).where(KbStandard.status == "published").order_by(KbStandard.id)
            )
            .scalars()
            .all()
        )

    def list_published_by_ids(self, ids: list[int]) -> list[KbStandard]:
        if not ids:
            return []
        return list(
            self.db.execute(
                select(KbStandard).where(
                    KbStandard.id.in_(ids), KbStandard.status == "published"
                )
            )
            .scalars()
            .all()
        )

    def get(self, standard_id: int) -> KbStandard | None:
        return self.db.get(KbStandard, standard_id)

    def get_by_code(self, code: str) -> KbStandard | None:
        return (
            self.db.execute(select(KbStandard).where(KbStandard.code == code)).scalars().first()
        )

    def get_by_name(self, name: str) -> KbStandard | None:
        return (
            self.db.execute(select(KbStandard).where(KbStandard.name == name)).scalars().first()
        )

    def add(self, standard: KbStandard) -> None:
        self.db.add(standard)

    def delete(self, standard: KbStandard) -> None:
        self.db.delete(standard)

    def list_existing_names(self) -> set[str]:
        """现有标准名称与别名集合，用于历史要求项沉淀时去重。"""
        names: set[str] = set()
        for standard in self.db.execute(select(KbStandard)).scalars().all():
            names.add(standard.name)
            if standard.aliases:
                try:
                    import json

                    names.update(json.loads(standard.aliases))
                except ValueError:
                    continue
        return names

    def list_requirement_names(self, limit: int) -> list[str]:
        """历史要求项名称（去重），作为标准库初始语料。"""
        stmt = (
            select(RequirementItem.name)
            .distinct()
            .order_by(RequirementItem.name)
            .limit(limit)
        )
        return [row[0] for row in self.db.execute(stmt).all()]
