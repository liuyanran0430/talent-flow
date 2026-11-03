"""向量库抽象接口。面向后续 JD/简历/标准条目的向量化检索场景。"""

from typing import Any, Protocol


class VectorStoreClient(Protocol):
    """向量库客户端协议：按 namespace 隔离不同业务集合（如 kb_standards / kb_docs）。"""

    def upsert(self, namespace: str, doc_id: str, text: str, metadata: dict[str, Any] | None = None) -> None:
        """写入/更新一条向量文档。"""
        ...

    def search(self, namespace: str, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """语义检索，返回 [{doc_id, text, metadata, score}, ...]。"""
        ...

    def delete(self, namespace: str, doc_id: str) -> None:
        """按 doc_id 删除。"""
        ...
