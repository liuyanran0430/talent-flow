"""Chroma 持久化向量库实现。

每个 namespace 对应一个 Chroma collection；向量由 DashScope embedding 生成后显式传入，
Chroma 只负责存储与近邻检索。入库/检索失败向上抛出，由 service 层统一降级。
"""

from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from ..core.config import settings
from .embedding import embed_query, embed_texts

_client: chromadb.ClientAPI | None = None


def _get_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(
            path=settings.VECTOR_STORE_PATH,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _client


class ChromaVectorStore:
    """基于 Chroma 的向量库实现（余弦距离，score = 1 - distance）。"""

    def _collection(self, namespace: str):
        return _get_client().get_or_create_collection(
            name=namespace,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert(
        self, namespace: str, doc_id: str, text: str, metadata: dict[str, Any] | None = None
    ) -> None:
        vector = embed_texts([text])[0]
        self._collection(namespace).upsert(
            ids=[doc_id],
            embeddings=[vector],
            documents=[text],
            metadatas=[metadata or {}],
        )

    def upsert_many(self, namespace: str, items: list[dict[str, Any]]) -> None:
        """批量写入：items 为 [{doc_id, text, metadata}]，向量按 RAG_REBUILD_BATCH 分批生成。"""
        collection = self._collection(namespace)
        batch = max(1, settings.RAG_REBUILD_BATCH)
        for start in range(0, len(items), batch):
            chunk = items[start : start + batch]
            vectors = embed_texts([it["text"] for it in chunk])
            collection.upsert(
                ids=[it["doc_id"] for it in chunk],
                embeddings=vectors,
                documents=[it["text"] for it in chunk],
                metadatas=[it.get("metadata") or {} for it in chunk],
            )

    def search(
        self,
        namespace: str,
        query: str,
        top_k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if top_k <= 0:
            return []
        vector = embed_query(query)
        kwargs: dict[str, Any] = {}
        if where:
            kwargs["where"] = where
        result = self._collection(namespace).query(
            query_embeddings=[vector],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
            **kwargs,
        )
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        hits: list[dict[str, Any]] = []
        for i, doc_id in enumerate(ids):
            hits.append(
                {
                    "doc_id": doc_id,
                    "text": documents[i] if i < len(documents) else "",
                    "metadata": metadatas[i] if i < len(metadatas) else {},
                    "score": 1.0 - float(distances[i]) if i < len(distances) else 0.0,
                }
            )
        return hits

    def delete(self, namespace: str, doc_id: str) -> None:
        self._collection(namespace).delete(ids=[doc_id])

    def reset(self, namespace: str) -> None:
        """清空某个 collection，用于全量重建前清理旧向量。"""
        try:
            _get_client().delete_collection(name=namespace)
        except Exception:
            # collection 不存在时无需处理，直接由后续 get_or_create 重建
            pass
