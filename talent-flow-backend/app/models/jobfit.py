from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class JobFit(Base):
    """候选人-要求项匹配结果（对应前端 ImportResume.jsx 的职位匹配建议列表）"""

    __tablename__ = "jobfits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True, comment="候选人 ID"
    )
    requirement_item_id: Mapped[int] = mapped_column(
        ForeignKey("requirement_items.id", ondelete="CASCADE"), nullable=False, index=True, comment="职位要求项 ID"
    )
    suggestion: Mapped[str] = mapped_column(String(16), default="证据不足", comment="匹配建议：满足/不满足/证据不足")
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True, comment="匹配依据")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
