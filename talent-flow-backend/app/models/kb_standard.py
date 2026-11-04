from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class KbStandard(Base):
    """岗位标准条目：组织级标准资料，作为 JD 要求项生成与简历匹配的判定依据。

    只有 status=published 的条目会向量化并参与检索；MySQL 为唯一事实源，
    向量库只是可随时重建的派生索引。
    """

    __tablename__ = "kb_standards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True, comment="标准编码")
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="标准名称，如 Python")
    category: Mapped[str] = mapped_column(String(32), default="技能", comment="技能/经验/学历/证书/软素质")
    level: Mapped[int] = mapped_column(Integer, default=3, comment="职级 1-5")
    type: Mapped[str] = mapped_column(String(16), default="必须", comment="必须/加分")
    importance: Mapped[str] = mapped_column(String(16), default="高", comment="高/中/低")
    standard: Mapped[str | None] = mapped_column(Text, nullable=True, comment="判定标准，描述如何衡量符合")
    required_evidence: Mapped[str | None] = mapped_column(Text, nullable=True, comment="需要候选人具备的证据")
    negative_signals: Mapped[str | None] = mapped_column(Text, nullable=True, comment="需要关注的反向信号")
    aliases: Mapped[str | None] = mapped_column(Text, nullable=True, comment="别名，JSON 数组字符串")
    job_family: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="适用职位族")
    source: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="来源，如历史要求项/HR 上传")
    status: Mapped[str] = mapped_column(
        String(16), default="draft", index=True, comment="draft/published/archived"
    )
    version: Mapped[int] = mapped_column(Integer, default=1, comment="版本号，发布后变更递增")
    embedding_model: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="向量化使用的模型")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
