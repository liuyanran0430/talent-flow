from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class RequirementTemplate(Base):
    """要求模板（对应前端 Requirements.jsx 的模板管理弹窗）"""

    __tablename__ = "requirement_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="模板名称")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="模板说明")
    usage_count: Mapped[int] = mapped_column(Integer, default=0, comment="使用次数")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class TemplateItem(Base):
    """模板下的要求项（结构与 requirement_items 一致，但归属模板）"""

    __tablename__ = "template_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("requirement_templates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    type: Mapped[str] = mapped_column(String(16), default="必须", comment="必须/加分")
    importance: Mapped[str] = mapped_column(String(16), default="高", comment="高/中/低")
    standard: Mapped[str | None] = mapped_column(Text, nullable=True, comment="判定标准")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
