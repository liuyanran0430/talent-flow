from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CandidateBase(BaseModel):
    # name 允许 NULL：上传待解析时未提取姓名，解析后由 LLM 写入
    name: str | None = Field(None, max_length=64)
    job_id: int | None = None
    status: str = Field("review", description="recommended/interview/review/hired/rejected/finish")
    info: str | None = None
    phone: str | None = Field(None, max_length=32)
    email: str | None = Field(None, max_length=128)
    experience: str | None = Field(None, max_length=32)
    resume_path: str | None = Field(None, max_length=255, description="简历文件路径")
    resume_hash: str | None = Field(None, max_length=64, description="简历内容哈希，用于查重")


class CandidateCreate(CandidateBase):
    pass


class CandidateUpdate(BaseModel):
    name: str | None = Field(None, max_length=64)
    job_id: int | None = None
    status: str | None = None
    info: str | None = None
    phone: str | None = None
    email: str | None = None
    experience: str | None = None
    resume_path: str | None = None


class CandidateOut(CandidateBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime
