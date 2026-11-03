"""空实现：向量库未配置时的降级桩。

所有方法静默 no-op 并记 warning，保证接入方（后续 RAG 增强流程）在未配置
向量库时不阻断主流程。MySQL 仍是唯一事实源，向量库只是可重建的派生索引。
"""

from typing import Any

from ..core.logging_config import get_logger

logger = get_logger("rag")


class NullVectorStore:
    def upsert(self, namespace: str, doc_id: str, text: str, metadata: dict[str, Any] | None = None) -> None:
        logger.warning("向量库未配置，upsert 被跳过 namespace=%s doc_id=%s", namespace, doc_id)

    def search(self, namespace: str, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        logger.warning("向量库未配置，search 返回空 namespace=%s", namespace)
        return []

    def delete(self, namespace: str, doc_id: str) -> None:
        logger.warning("向量库未配置，delete 被跳过 namespace=%s doc_id=%s", namespace, doc_id)
