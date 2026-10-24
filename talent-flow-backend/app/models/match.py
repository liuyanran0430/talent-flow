from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, SmallInteger, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class Match(Base):
    """岗位-候选人匹配打分"""

    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True, comment="岗位 ID"
    )
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True, comment="候选人 ID"
    )
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, comment="匹配打分 0-100")
    must_satisfied: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, comment="基本项满足个数")
    must_unsatisfied: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, comment="基本项不满足个数")
    must_insufficient: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, comment="基本项证据不足个数")
    bonus_satisfied: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, comment="加分项满足个数")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
