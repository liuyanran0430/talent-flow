from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class JobFitBase(BaseModel):
    candidate_id: int = Field(..., description="候选人 ID")
    requirement_item_id: int = Field(..., description="职位要求项 ID")
    suggestion: str = Field("证据不足", description="匹配建议：满足/不满足/证据不足")
    evidence: str | None = Field(None, description="匹配依据")


class JobFitCreate(JobFitBase):
    pass


class JobFitUpdate(BaseModel):
    suggestion: str | None = Field(None, description="匹配建议：满足/不满足/证据不足")
    evidence: str | None = Field(None, description="匹配依据")


class JobFitOut(JobFitBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime
