from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class KbDocument(Base):
    """制度知识库文档：版本与状态管理，MySQL 为唯一事实源。"""

    __tablename__ = "kb_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(
        String(16), unique=True, nullable=False, index=True, comment="文档编号，如 DOC-001"
    )
    document_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="文档名称")
    domain: Mapped[str] = mapped_column(String(32), nullable=False, index=True, comment="知识领域")
    file_path: Mapped[str | None] = mapped_column(String(256), nullable=True, comment="源文件路径")
    version: Mapped[str] = mapped_column(String(16), default="1.0", comment="版本号")
    status: Mapped[str] = mapped_column(
        String(16), default="current", index=True, comment="current/archived"
    )
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, comment="分段数量")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class KbSegment(Base):
    """制度知识库分段：检索与引用的事实源，segment_id 稳定不漂移。"""

    __tablename__ = "kb_segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(
        String(16), nullable=False, index=True, comment="所属文档编号"
    )
    segment_id: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, index=True, comment="片段编号 DOC-001-S001"
    )
    chunk_no: Mapped[int] = mapped_column(Integer, nullable=False, comment="块序号，从 1 起")
    section: Mapped[str | None] = mapped_column(String(256), nullable=True, comment="所属章节路径")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="分段正文")
    char_count: Mapped[int] = mapped_column(Integer, default=0, comment="字符数")
    type: Mapped[str] = mapped_column(String(16), default="text", comment="text/table/faq")
    version: Mapped[str] = mapped_column(String(16), default="1.0", comment="版本号")
    status: Mapped[str] = mapped_column(
        String(16), default="current", index=True, comment="current/archived"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
