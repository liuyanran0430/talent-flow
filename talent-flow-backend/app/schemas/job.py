from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class JobStatus(str, Enum):
    open = "open"
    urgent = "urgent"
    paused = "paused"
    closed = "closed"


class JobBase(BaseModel):
    name: str = Field(..., max_length=128, description="职位名称")
    department_id: int | None = None
    headcount: int = Field(1, ge=1, description="招聘人数")
    status: JobStatus = JobStatus.open
    description: str | None = Field(None, description="职位描述")


class JobCreate(JobBase):
    pass


class JobUpdate(BaseModel):
    name: str | None = Field(None, max_length=128)
    department_id: int | None = None
    headcount: int | None = Field(None, ge=1)
    status: JobStatus | None = None
    description: str | None = None


class JobOut(JobBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime
    status_label: str | None = None  # 由 service 注入中文标签
    dept_label: str | None = None  # 由 service 从 department 关联注入


class JobWithStats(JobOut):
    """带候选人聚合统计的职位（用于职位列表）"""

    hired: int = 0
    candidates: int = 0
    progress: int = 0


STATUS_LABEL_MAP: dict[JobStatus, str] = {
    JobStatus.open: "招聘中",
    JobStatus.urgent: "需推进",
    JobStatus.paused: "已暂停",
    JobStatus.closed: "已关闭",
}
