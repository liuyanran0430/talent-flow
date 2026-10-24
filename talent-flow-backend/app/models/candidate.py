from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class Candidate(Base):
    """候选人"""

    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=True, comment="姓名")
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="review", comment="recommended/interview/review/hired/rejected/finish")
    info: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="经验·公司·活跃度")
    phone: Mapped[str | None] = mapped_column(String(32), nullable=False, comment="手机号")
    email: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="邮箱")
    experience: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="工作年限区间")
    resume_path: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="简历文件路径")
    resume_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True, comment="简历内容 SHA256，用于查重")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
