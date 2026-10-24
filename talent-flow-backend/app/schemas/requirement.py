from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RequirementItemBase(BaseModel):
    job_id: int = Field(..., description="所属职位 ID")
    name: str = Field(..., max_length=128, description="要求项名称，如 Python 基础")
    type: str = Field("必须", description="必须/加分")
    importance: str = Field("高", description="高/中/低")
    standard: str | None = Field(None, description="判定标准")


class RequirementItemCreate(RequirementItemBase):
    pass


class RequirementItemUpdate(BaseModel):
    name: str | None = Field(None, max_length=128)
    type: str | None = None
    importance: str | None = None
    standard: str | None = None


class RequirementItemOut(RequirementItemBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime


class RequirementItemGen(BaseModel):
    """AI 生成的要求项（未落库，弹窗内可编辑，确认后批量应用）"""

    name: str = Field(..., max_length=128, description="要求项名称")
    type: str = Field("必须", description="必须/加分")
    importance: str = Field("中", description="高/中/低")
    standard: str | None = Field(None, description="判定标准")


class RequirementBatchCreate(BaseModel):
    """批量覆盖写入要求项（AI 生成结果编辑确认后应用）"""

    items: list[RequirementItemGen] = Field(..., min_length=1, description="要求项集合，整体覆盖当前职位要求")


class RecalculatePayload(BaseModel):
    """要求配置变化后重算相关候选人的算法参数（与前端 ALGO_SETTINGS 保持一致）"""

    weights: dict[str, float] = Field(
        default_factory=lambda: {"高": 45, "中": 35, "低": 20},
        description="重要程度权重：高/中/低 → 0-100",
    )
    must_gate: float = Field(80, description="必备项准入门槛（满足率百分比）")
    recommend_threshold: float = Field(75, description="推荐分数阈值")
