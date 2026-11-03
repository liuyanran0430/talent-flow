"""向量库封装：VectorStoreClient 工厂。

本期仅提供 NullVectorStore 空实现（接口先行、接线后置）；
后续接入 Chroma 等实现时按 settings.VECTOR_STORE_BACKEND 切换。
"""

from ..core.config import settings
from .base import VectorStoreClient
from .null_store import NullVectorStore

__all__ = ["VectorStoreClient", "NullVectorStore", "get_vector_store"]


def get_vector_store() -> VectorStoreClient:
    backend = getattr(settings, "VECTOR_STORE_BACKEND", "null")
    if backend == "null":
        return NullVectorStore()
    raise ValueError(f"未知的向量库实现：{backend}")
