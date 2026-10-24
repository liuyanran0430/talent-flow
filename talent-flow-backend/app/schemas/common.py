from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一响应封装"""

    code: int = 0
    message: str = "ok"
    data: T | None = None

    @classmethod
    def ok(cls, data: T | None = None, message: str = "ok") -> "ApiResponse[T]":
        return cls(code=0, message=message, data=data)

    @classmethod
    def fail(cls, message: str, code: int = 1, data: T | None = None) -> "ApiResponse[T]":
        return cls(code=code, message=message, data=data)


class PageParams(BaseModel):
    """分页查询参数"""

    page: int = Field(1, ge=1, description="页码，从 1 开始")
    page_size: int = Field(20, ge=1, le=100, description="每页条数")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class PageResponse(BaseModel, Generic[T]):
    """分页响应"""

    total: int
    page: int
    page_size: int
    items: list[T]
