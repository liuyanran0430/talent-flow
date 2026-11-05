from pydantic import BaseModel, Field


class QaAskRequest(BaseModel):
    """问答入参；会话不落库，history / pending_intent 由前端回传。"""

    question: str = Field(..., min_length=1, max_length=2000, description="用户问题")
    session_id: str | None = Field(None, max_length=64, description="前端生成的会话 id，仅用于日志串联")
    history: list[dict] | None = Field(None, description="最近若干轮问答摘要，默认最多 3 轮")
    pending_intent: dict | None = Field(None, description="上一轮追问意图，原样回传")
