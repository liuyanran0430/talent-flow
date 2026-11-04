"""向量库封装：VectorStoreClient 工厂。

按 settings.VECTOR_STORE_BACKEND 选择实现：
- chroma：本地持久化向量库（默认，向量由 DashScope 生成）
- null：空实现，RAG 关闭或异常时降级使用
"""

from ..core.config import settings
from .base import VectorStoreClient
from .chroma_store import ChromaVectorStore
from .null_store import NullVectorStore

__all__ = ["VectorStoreClient", "NullVectorStore", "ChromaVectorStore", "get_vector_store"]


def get_vector_store() -> VectorStoreClient:
    backend = (settings.VECTOR_STORE_BACKEND or "null").lower()
    if backend == "null":
        return NullVectorStore()
    if backend == "chroma":
        return ChromaVectorStore()
    raise ValueError(f"未知的向量库实现：{backend}")
