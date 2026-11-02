from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator


class CandidateBase(BaseModel):
    # name 允许 NULL：上传待解析时未提取姓名，解析后由 LLM 写入
    name: str | None = Field(None, max_length=64)
    status: str = Field("review", description="pending/processing/review/finish")
    phone: str | None = Field(None, max_length=32)
    email: str | None = Field(None, max_length=128)
    review_note: str | None = Field(None, description="HR 复核意见")
    # 以下字段物理上存储在 resume_infos 表，API 层拍平返回/接收以保持契约不变
    job_id: int | None = None
    experience: str | None = Field(None, max_length=32)
    info: str | None = None


class CandidateCreate(CandidateBase):
    resume_path: str | None = Field(None, max_length=255, description="简历文件路径")
    resume_hash: str | None = Field(None, max_length=64, description="简历内容哈希，用于查重")


class CandidateUpdate(BaseModel):
    name: str | None = Field(None, max_length=64)
    status: str | None = None
    phone: str | None = None
    email: str | None = None
    review_note: str | None = Field(None, description="HR 复核意见")
    # 简历侧字段：由 service 路由到 resume_infos
    job_id: int | None = None
    experience: str | None = None
    info: str | None = None


class CandidateOut(CandidateBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime
    resume_path: str | None = Field(None, description="简历文件路径")
    # 原始 JSON 字符串（保留给需要做二次解析的场景，前端通常不直接用）
    analysis: str | None = Field(None, description="AI 分析原始 JSON")

    @model_validator(mode="before")
    @classmethod
    def _flatten_resume(cls, data: Any) -> Any:
        """ORM 对象 → 拍平：把 candidate.resume 上的简历侧字段合并到顶层。"""
        resume = getattr(data, "resume", None)
        if resume is None:
            return data
        if isinstance(data, dict):
            merged = dict(data)
        else:
            merged = {
                "id": data.id,
                "name": data.name,
                "status": data.status,
                "phone": data.phone,
                "email": data.email,
                "created_at": data.created_at,
                "updated_at": data.updated_at,
            }
        merged.update(
            {
                "job_id": resume.job_id,
                "experience": resume.experience,
                "info": resume.info,
                "review_note": resume.review_note,
                "resume_path": resume.resume_path,
                "analysis": resume.analysis,
            }
        )
        return merged

    @computed_field
    @property
    def advantages(self) -> list[dict[str, Any]]:
        """结构化的优势列表 [{point, evidence}]，无优势时返回空数组"""
        return self._parsed_analysis.get("advantages", [])

    @computed_field
    @property
    def risks(self) -> list[dict[str, Any]]:
        """结构化的风险列表 [{point, evidence}]，无风险时返回空数组"""
        return self._parsed_analysis.get("risks", [])

    @property
    def _parsed_analysis(self) -> dict[str, Any]:
        if not self.analysis:
            return {"advantages": [], "risks": []}
        import json as _json

        try:
            data = _json.loads(self.analysis)
        except (TypeError, ValueError):
            return {"advantages": [], "risks": []}
        return {
            "advantages": data.get("advantages") or [],
            "risks": data.get("risks") or [],
        }
