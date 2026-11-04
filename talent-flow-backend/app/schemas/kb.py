"""岗位标准知识库的请求/响应结构"""

import json

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class KbStandardCreate(BaseModel):
    code: str | None = Field(None, max_length=64, description="标准编码，不填由服务端生成")
    name: str = Field(..., max_length=128, description="标准名称，如 Python")
    category: str = Field("技能", max_length=32, description="技能/经验/学历/证书/软素质")
    level: int = Field(3, ge=1, le=5, description="职级 1-5")
    type: str = Field("必须", description="必须/加分")
    importance: str = Field("高", description="高/中/低")
    standard: str | None = Field(None, description="判定标准")
    required_evidence: str | None = Field(None, description="需要的证据")
    negative_signals: str | None = Field(None, description="需关注的反向信号")
    aliases: list[str] = Field(default_factory=list, description="别名")
    job_family: str | None = Field(None, max_length=64, description="适用职位族")
    source: str | None = Field(None, max_length=128, description="来源")


class KbStandardUpdate(BaseModel):
    name: str | None = Field(None, max_length=128)
    category: str | None = Field(None, max_length=32)
    level: int | None = Field(None, ge=1, le=5)
    type: str | None = None
    importance: str | None = None
    standard: str | None = None
    required_evidence: str | None = None
    negative_signals: str | None = None
    aliases: list[str] | None = None
    job_family: str | None = Field(None, max_length=64)
    source: str | None = Field(None, max_length=128)


class KbStandardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    category: str
    level: int
    type: str
    importance: str
    standard: str | None = None
    required_evidence: str | None = None
    negative_signals: str | None = None
    aliases: list[str] = Field(default_factory=list)
    job_family: str | None = None
    source: str | None = None
    status: str
    version: int
    embedding_model: str | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("aliases", mode="before")
    @classmethod
    def _parse_aliases(cls, value):
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, list) else []
            except ValueError:
                return []
        return value or []


class KbSearchHit(BaseModel):
    standard_id: int
    code: str
    name: str
    standard: str | None = None
    score: float = Field(..., description="相似度，0-1")


class KbSearchResult(BaseModel):
    query: str
    hits: list[KbSearchHit] = Field(default_factory=list)
    degraded: bool = Field(False, description="是否走了降级（未实际检索）")


class KbImportRequest(BaseModel):
    limit: int = Field(200, ge=1, le=1000, description="最多沉淀多少条历史要求项")


class KbImportResult(BaseModel):
    created: int = Field(0, description="新沉淀的标准数")
    skipped: int = Field(0, description="与已有标准重名而跳过的数量")


class KbReindexResult(BaseModel):
    total: int = Field(0, description="已发布标准总数")
    indexed: int = Field(0, description="成功向量化的数量")
    failed: int = Field(0, description="向量化失败的数量")
    degraded: bool = Field(False, description="是否因 RAG 不可用而降级")
