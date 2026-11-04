"""DashScope 文本向量化封装（OpenAI 兼容接口）。

只负责「文本 → 向量」，不做降级：调用失败直接抛 EmbeddingError，
由上层检索/索引服务捕获后回退到纯 LLM 逻辑，避免在底层吞掉异常。
"""

from openai import OpenAI

from ..core.config import settings
from ..core.logging_config import get_logger

logger = get_logger("rag")

_client: OpenAI | None = None


class EmbeddingError(Exception):
    """向量化不可用：未配置密钥、服务异常或返回为空"""


def _get_client() -> OpenAI:
    global _client
    if not settings.EMBEDDING_API_KEY:
        raise EmbeddingError("未配置 EMBEDDING_API_KEY，RAG 检索降级")
    if _client is None:
        _client = OpenAI(api_key=settings.EMBEDDING_API_KEY, base_url=settings.EMBEDDING_API_BASE)
    return _client


def is_available() -> bool:
    """是否具备向量化条件（开关 + 密钥）。"""
    return bool(settings.RAG_ENABLED and settings.EMBEDDING_API_KEY)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """批量向量化，返回与输入顺序一致的向量列表。"""
    if not texts:
        return []
    if not is_available():
        raise EmbeddingError("RAG 未启用或未配置 EMBEDDING_API_KEY")
    response = _get_client().embeddings.create(model=settings.EMBEDDING_MODEL, input=texts)
    vectors = [item.embedding for item in response.data]
    if len(vectors) != len(texts):
        raise EmbeddingError(f"向量数量不匹配：期望 {len(texts)}，实际 {len(vectors)}")
    return vectors


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
