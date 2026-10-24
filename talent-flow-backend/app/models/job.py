from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class Job(Base):
    """职位"""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="职位名称")
    department_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("departments.id"), nullable=True, index=True, comment="关联部门")
    headcount: Mapped[int] = mapped_column(Integer, default=1, comment="招聘人数")
    status: Mapped[str] = mapped_column(String(16), default="open", comment="open/paused/closed")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="职位描述")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    department: Mapped["Department | None"] = relationship(back_populates="jobs")
