"""前端错误日志上报的请求结构"""
from typing import Literal, Optional

from pydantic import BaseModel, Field


class FrontendLog(BaseModel):
    """前端上报的一条日志（仅 warn/error 级别会上报，避免刷屏）"""

    level: Literal["warn", "error"] = Field("error", description="日志级别")
    tag: str = Field("app", max_length=64, description="模块标签，如页面或组件名")
    message: str = Field(..., max_length=4000, description="日志内容")
    stack: Optional[str] = Field(None, max_length=8000, description="错误堆栈（如有）")
    page: Optional[str] = Field(None, max_length=128, description="当前页面路由/区块")
    session_id: Optional[str] = Field(None, max_length=64, description="前端会话 id，用于串联同一用户操作")
    trace_id: Optional[str] = Field(None, max_length=64, description="前端当前操作的 trace id，与后端请求日志对齐")
    url: Optional[str] = Field(None, max_length=500, description="触发日志时的页面地址")
    user_agent: Optional[str] = Field(None, max_length=500, description="浏览器 UA")
