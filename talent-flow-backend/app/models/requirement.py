from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class RequirementItem(Base):
    """职位要求项（一个职位有多条要求项，对应前端 Requirements.jsx 的要求列表）"""

    __tablename__ = "requirement_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="要求项名称，如 Python 基础")
    type: Mapped[str] = mapped_column(String(16), default="必须", comment="必须/加分")
    importance: Mapped[str] = mapped_column(String(16), default="高", comment="高/中/低")
    standard: Mapped[str | None] = mapped_column(Text, nullable=True, comment="判定标准")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
