import json
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class ResumeInfo(Base):
    """简历信息（"这份简历"的解析结果，与候选人一对一）"""

    __tablename__ = "resume_infos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, unique=True, index=True, comment="关联候选人"
    )
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, comment="意向职位")
    experience: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="工作年限区间")
    resume_path: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="简历文件路径")
    resume_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True, comment="简历内容 SHA256，用于查重")
    info: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="解析过程提示信息")
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True, comment="HR 复核意见")
    # AI 整体分析结论：优势与风险（带证据）。存储为 JSON 字符串。
    # 结构：{"advantages": [{"point": str, "evidence": str}], "risks": [{"point": str, "evidence": str}]}
    analysis: Mapped[str | None] = mapped_column(Text, nullable=True, comment="AI 分析结论（JSON）")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    candidate: Mapped["Candidate"] = relationship("Candidate", back_populates="resume")

    def parsed_analysis(self) -> dict[str, list[dict[str, Any]]]:
        """安全解析 analysis 列，返回 {advantages, risks}，缺省字段自动补空列表。"""
        if not self.analysis:
            return {"advantages": [], "risks": []}
        try:
            data = json.loads(self.analysis)
        except (TypeError, ValueError):
            return {"advantages": [], "risks": []}
        return {
            "advantages": data.get("advantages") or [],
            "risks": data.get("risks") or [],
        }
