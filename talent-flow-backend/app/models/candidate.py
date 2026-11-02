from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:  # 仅类型检查使用，运行期由字符串 relationship 解析
    from .resume import ResumeInfo


class Candidate(Base):
    """候选人（"人"的信息，一人一行）"""

    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="姓名")
    status: Mapped[str] = mapped_column(String(16), default="review", comment="pending/processing/review/finish")
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="手机号")
    email: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="邮箱")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # 一对一简历信息（当前业务一人一份简历；uselist=False 表示一对一）
    resume: Mapped["ResumeInfo | None"] = relationship(
        "ResumeInfo", back_populates="candidate", uselist=False, cascade="all, delete-orphan"
    )
