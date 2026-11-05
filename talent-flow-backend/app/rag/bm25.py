"""BM25 关键词检索（内存倒排索引）。

与向量检索形成互补：向量擅长语义近似，BM25 擅长专有名词精确匹配。
标准条目量级小（千级），纯 Python 实现即可，不引入外部搜索服务。

索引生命周期：
- 应用启动 / 全量重建时从已发布标准构建
- 发布标准时增量写入
- 归档/删除标准时移除
"""

import math
import re
from collections import defaultdict

from ..core.config import settings
from ..core.logging_config import get_logger

logger = get_logger("rag")

# BM25 参数
_K1 = 1.5
_B = 0.75

# 英文/数字/符号切分正则；中文交给 jieba
_TOKEN_SPLIT_RE = re.compile(r"[a-zA-Z0-9]+")

_jieba_available: bool | None = None


def _ensure_jieba() -> bool:
    """惰性检查 jieba 是否可用，结果缓存。"""
    global _jieba_available
    if _jieba_available is not None:
        return _jieba_available
    try:
        import jieba  # noqa: F401

        _jieba_available = True
    except ImportError:
        logger.warning("jieba 未安装，BM25 仅对英文/数字/标点切分，中文检索效果下降")
        _jieba_available = False
    return _jieba_available


def tokenize(text: str) -> list[str]:
    """分词：中文用 jieba，英文/数字按正则切分，统一小写。"""
    if not text:
        return []
    tokens: list[str] = []
    # 英文/数字片段
    for m in _TOKEN_SPLIT_RE.finditer(text):
        tokens.append(m.group(0).lower())
    # 中文片段
    if _ensure_jieba():
        import jieba

        chinese_parts = _TOKEN_SPLIT_RE.sub(" ", text)
        for tok in jieba.cut(chinese_parts):
            tok = tok.strip()
            if tok and not _TOKEN_SPLIT_RE.fullmatch(tok):
                tokens.append(tok.lower())
    else:
        # jieba 不可用时，退化为按单字切分中文（粗粒度但能命中）
        chinese_parts = _TOKEN_SPLIT_RE.sub("", text)
        for ch in chinese_parts:
            if ch.strip():
                tokens.append(ch)
    return tokens


class BM25Index:
    """内存 BM25 倒排索引，doc_id 为字符串。"""

    def __init__(self) -> None:
        self._doc_tokens: dict[str, list[str]] = {}
        self._doc_len: dict[str, int] = {}
        self._term_freq: dict[str, dict[str, int]] = defaultdict(dict)  # term -> {doc_id: freq}
        self._avgdl: float = 0.0
        self._N: int = 0

    def _recompute_stats(self) -> None:
        self._N = len(self._doc_tokens)
        total = sum(self._doc_len.values())
        self._avgdl = total / self._N if self._N else 0.0

    def upsert(self, doc_id: str, text: str) -> None:
        """写入或更新一条文档。"""
        tokens = tokenize(text)
        # 先移除旧的
        if doc_id in self._doc_tokens:
            self._remove_internal(doc_id)
        self._doc_tokens[doc_id] = tokens
        self._doc_len[doc_id] = len(tokens)
        freq: dict[str, int] = defaultdict(int)
        for t in tokens:
            freq[t] += 1
        for term, f in freq.items():
            self._term_freq[term][doc_id] = f
        self._recompute_stats()

    def _remove_internal(self, doc_id: str) -> None:
        tokens = self._doc_tokens.pop(doc_id, None)
        self._doc_len.pop(doc_id, None)
        if tokens:
            for term in set(tokens):
                self._term_freq[term].pop(doc_id, None)
                if not self._term_freq[term]:
                    del self._term_freq[term]

    def delete(self, doc_id: str) -> None:
        self._remove_internal(doc_id)
        self._recompute_stats()

    def clear(self) -> None:
        self._doc_tokens.clear()
        self._doc_len.clear()
        self._term_freq.clear()
        self._avgdl = 0.0
        self._N = 0

    def rebuild(self, docs: list[tuple[str, str]]) -> None:
        """全量重建：docs 为 [(doc_id, text), ...]。"""
        self.clear()
        for doc_id, text in docs:
            tokens = tokenize(text)
            self._doc_tokens[doc_id] = tokens
            self._doc_len[doc_id] = len(tokens)
            freq: dict[str, int] = defaultdict(int)
            for t in tokens:
                freq[t] += 1
            for term, f in freq.items():
                self._term_freq[term][doc_id] = f
        self._recompute_stats()

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        """BM25 检索，返回 [{doc_id, score}]，score 归一化到 [0,1]。"""
        query_terms = tokenize(query)
        if not query_terms or self._N == 0:
            return []
        scores: dict[str, float] = defaultdict(float)
        for term in set(query_terms):
            postings = self._term_freq.get(term)
            if not postings:
                continue
            n = len(postings)
            idf = math.log(1 + (self._N - n + 0.5) / (n + 0.5))
            for doc_id, f in postings.items():
                dl = self._doc_len.get(doc_id, 0)
                denom = f + _K1 * (1 - _B + _B * (dl / self._avgdl if self._avgdl else 0))
                scores[doc_id] += idf * (f * (_K1 + 1)) / denom
        if not scores:
            return []
        max_score = max(scores.values())
        if max_score <= 0:
            return []
        results = [
            {"doc_id": doc_id, "score": score / max_score}
            for doc_id, score in scores.items()
        ]
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]


# 全局单例：岗位标准 BM25 索引
_standard_bm25 = BM25Index()


def get_standard_bm25() -> BM25Index:
    return _standard_bm25


def is_bm25_available() -> bool:
    """BM25 是否可用（开关开启且索引有数据）。"""
    if not settings.RAG_BM25_ENABLED:
        return False
    return _standard_bm25._N > 0


def bm25_search_standards(query: str, top_k: int = 10) -> list[dict]:
    """检索岗位标准 BM25 索引，返回 [{doc_id, score}]。

    索引未构建或不可用时返回空列表，由调用方降级为纯向量检索。
    """
    if not settings.RAG_BM25_ENABLED:
        return []
    try:
        return _standard_bm25.search(query, top_k=top_k)
    except Exception as e:
        logger.warning("BM25 检索失败，降级为纯向量：%s", e)
        return []


# 全局单例：制度知识库分段 BM25 索引（kb_docs 命名空间）
_doc_bm25 = BM25Index()


def get_doc_bm25() -> BM25Index:
    return _doc_bm25


def bm25_search_docs(query: str, top_k: int = 10) -> list[dict]:
    """检索制度分段 BM25 索引，索引未构建或不可用时返回空列表。"""
    if not settings.RAG_BM25_ENABLED:
        return []
    try:
        return _doc_bm25.search(query, top_k=top_k)
    except Exception as e:
        logger.warning("制度 BM25 检索失败，降级为纯向量：%s", e)
        return []


def is_doc_bm25_available() -> bool:
    return settings.RAG_BM25_ENABLED and _doc_bm25._N > 0
