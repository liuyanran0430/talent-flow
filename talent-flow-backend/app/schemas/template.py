from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TemplateItemBase(BaseModel):
    name: str = Field(..., max_length=128, description="要求项名称")
    type: str = Field("必须", description="必须/加分")
    importance: str = Field("高", description="高/中/低")
    standard: str | None = Field(None, description="判定标准")


class TemplateItemCreate(TemplateItemBase):
    pass


class TemplateItemUpdate(BaseModel):
    name: str | None = Field(None, max_length=128)
    type: str | None = None
    importance: str | None = None
    standard: str | None = None


class TemplateItemOut(TemplateItemBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    template_id: int
    created_at: datetime
    updated_at: datetime


class RequirementTemplateBase(BaseModel):
    name: str = Field(..., max_length=128, description="模板名称")
    description: str | None = Field(None, description="模板说明")


class RequirementTemplateCreate(RequirementTemplateBase):
    items: list[TemplateItemCreate] = Field(
        default_factory=list, description="模板下的要求项，可随模板一起创建"
    )


class RequirementTemplateUpdate(BaseModel):
    name: str | None = Field(None, max_length=128)
    description: str | None = None


class RequirementTemplateOut(RequirementTemplateBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    usage_count: int
    created_at: datetime
    updated_at: datetime
    items: list[TemplateItemOut] = Field(default_factory=list)


class ApplyTemplateRequest(BaseModel):
    job_id: int = Field(..., description="目标职位 ID，模板项将复制为该职位的要求项")
