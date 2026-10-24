from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DepartmentBase(BaseModel):
    name: str = Field(..., max_length=64)
    responsibility: str | None = Field(None, max_length=500)


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentUpdate(BaseModel):
    name: str | None = Field(None, max_length=64)
    responsibility: str | None = Field(None, max_length=500)


class DepartmentOut(DepartmentBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime
