from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MatchBase(BaseModel):
    job_id: int = Field(..., description="岗位 ID")
    candidate_id: int = Field(..., description="候选人 ID")
    score: int = Field(0, ge=0, le=100, description="匹配打分 0-100")
    must_satisfied: int = Field(0, ge=0, description="基本项满足个数")
    must_unsatisfied: int = Field(0, ge=0, description="基本项不满足个数")
    must_insufficient: int = Field(0, ge=0, description="基本项证据不足个数")
    bonus_satisfied: int = Field(0, ge=0, description="加分项满足个数")


class MatchCreate(MatchBase):
    pass


class MatchUpdate(BaseModel):
    score: int | None = Field(None, ge=0, le=100, description="匹配打分 0-100")
    must_satisfied: int | None = Field(None, ge=0, description="基本项满足个数")
    must_unsatisfied: int | None = Field(None, ge=0, description="基本项不满足个数")
    must_insufficient: int | None = Field(None, ge=0, description="基本项证据不足个数")
    bonus_satisfied: int | None = Field(None, ge=0, description="加分项满足个数")


class MatchOut(MatchBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime
