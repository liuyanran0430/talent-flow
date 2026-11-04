from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class AsyncTask(Base):
    """异步任务：调用 LLM 的接口立即返回 request_id，前端按 request_id 轮询状态与结果"""

    __tablename__ = "async_tasks"

    request_id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="任务唯一标识，返回给前端轮询")
    task_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True, comment="任务类型，如 requirement_generate / resume_parse")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True, comment="pending/running/success/failed")
    result: Mapped[str | None] = mapped_column(Text, nullable=True, comment="成功结果（JSON 字符串）")
    error: Mapped[str | None] = mapped_column(Text, nullable=True, comment="失败原因")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
