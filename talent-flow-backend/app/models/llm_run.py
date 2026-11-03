from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class LLMRun(Base):
    """一次模型调用的运行记录：模型、token 用量、耗时与状态。

    trace_id 与请求/后台任务日志对齐，便于把某次操作产生的所有模型调用串起来。
    """

    __tablename__ = "llm_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True, comment="关联的操作 trace id")
    model: Mapped[str] = mapped_column(String(128), nullable=False, default="-", comment="模型名称")
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="输入 token 数")
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="输出 token 数")
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="总 token 数")
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="调用耗时（毫秒）")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="success", comment="success/error")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="失败原因")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
