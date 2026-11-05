"""制度分段混合检索与证据整理。

两路召回：
- 向量路：kb_docs 集合，余弦相似度（1 - distance）；
- 关键词路：BM25 内存索引（jieba 分词）。

融合：final = 0.55 * v_norm + 0.45 * b_norm，阈值 0.55；
单路豁免：max(v_norm, b_norm) >= 0.75 时最多保留 1 条，未进 TopK 则替换末位。
"""

from sqlalchemy import select

from ..core.config import settings
from ..core.logging_config import get_logger
from ..models import KbDocument, KbSegment
from ..rag import get_vector_store
from ..rag.bm25 import bm25_search_docs

logger = get_logger("qa")

DOC_NAMESPACE = "kb_docs"


def _vector_search(query: str, pool: int, domain: str | None) -> list[dict]:
    where: dict = {"status": {"$eq": "current"}}
    if domain:
        where = {"$and": [{"status": {"$eq": "current"}}, {"domain": {"$eq": domain}}]}
    try:
        return get_vector_store().search(DOC_NAMESPACE, query, top_k=pool, where=where)
    except TypeError:
        # 兼容不支持 where 的实现：先召回再在 MySQL 侧过滤
        try:
            return get_vector_store().search(DOC_NAMESPACE, query, top_k=pool)
        except Exception as e:
            logger.warning("制度向量检索失败，仅走 BM25：%s", e)
            return []
    except Exception as e:
        logger.warning("制度向量检索失败，仅走 BM25：%s", e)
        return []


def _load_segments(db, segment_ids: list[str], domain: str | None) -> dict[str, dict]:
    if not segment_ids:
        return {}
    rows = db.execute(
        select(KbSegment, KbDocument)
        .join(KbDocument, KbDocument.document_id == KbSegment.document_id)
        .where(KbSegment.segment_id.in_(segment_ids))
    ).all()
    result: dict[str, dict] = {}
    for segment, document in rows:
        if segment.status != "current" or document.status != "current":
            continue
        if domain and document.domain != domain:
            continue
        result[segment.segment_id] = {
            "segment_id": segment.segment_id,
            "document_id": segment.document_id,
            "document_name": document.document_name,
            "domain": document.domain,
            "section": segment.section or "",
            "content": segment.content,
            "type": segment.type,
        }
    return result


def retrieve_doc_segments(db, query: str, domain: str | None = None) -> list[dict]:
    """混合检索制度分段，返回按综合分降序的命中列表（含 bypass 标记）。"""
    query = (query or "").strip()
    if not query or not settings.QA_ENABLED:
        return []
    top_k = settings.QA_DOC_TOP_K
    pool = max(settings.QA_DOC_CANDIDATE_POOL, top_k)

    vector_hits = _vector_search(query, pool, domain)
    bm25_hits = bm25_search_docs(query, top_k=pool)

    vector_scores: dict[str, float] = {}
    for hit in vector_hits:
        vector_scores[str(hit.get("doc_id"))] = max(0.0, min(1.0, float(hit.get("score") or 0)))
    bm25_scores: dict[str, float] = {}
    for hit in bm25_hits:
        bm25_scores[str(hit.get("doc_id"))] = max(0.0, min(1.0, float(hit.get("score") or 0)))

    if not vector_scores and not bm25_scores:
        return []

    candidates = _load_segments(db, list(set(vector_scores) | set(bm25_scores)), domain)
    if not candidates:
        return []

    max_bm25 = max(bm25_scores.values(), default=0.0)
    scored: list[dict] = []
    bypass_candidates: list[dict] = []
    for segment_id, info in candidates.items():
        v_score = vector_scores.get(segment_id, 0.0)
        raw_b = bm25_scores.get(segment_id, 0.0)
        b_score = raw_b / max_bm25 if max_bm25 else 0.0
        final_score = settings.QA_DOC_VECTOR_WEIGHT * v_score + settings.QA_DOC_BM25_WEIGHT * b_score
        best_path = max(v_score, b_score)
        hit = {
            **info,
            "score": round(final_score, 4),
            "vector_score": round(v_score, 4),
            "bm25_score": round(b_score, 4),
        }
        if final_score >= settings.QA_DOC_MIN_SCORE:
            scored.append(hit)
        elif best_path >= settings.QA_SINGLE_PATH_BYPASS_SCORE:
            hit["best_path"] = round(best_path, 4)
            bypass_candidates.append(hit)

    scored.sort(key=lambda h: h["score"], reverse=True)
    bypass_candidates.sort(key=lambda h: h["best_path"], reverse=True)
    selected_bypass = bypass_candidates[: max(0, settings.QA_SINGLE_PATH_BYPASS_MAX)]

    hits = scored[:top_k]
    for hit in selected_bypass:
        hit["bypass"] = True
        hit.pop("best_path", None)
        if hit["segment_id"] in {h["segment_id"] for h in hits}:
            continue
        if len(hits) >= top_k:
            hits[-1] = hit
        else:
            hits.append(hit)
    hits.sort(key=lambda h: h["score"], reverse=True)
    return hits


def build_evidence(hits: list[dict], max_chars: int | None = None) -> list[dict]:
    """整理证据：缺字段直接丢弃，按 score 降序编号 Sx，总长超限截断。"""
    if not hits:
        return []
    limit = settings.QA_DOC_MAX_EVIDENCE_CHARS if max_chars is None else max_chars
    ordered = sorted(hits, key=lambda h: h.get("score", 0.0), reverse=True)
    evidence: list[dict] = []
    used = 0
    for hit in ordered:
        required = ("document_name", "document_id", "segment_id", "score", "content")
        if any(hit.get(key) in (None, "") for key in required):
            continue
        remaining = limit - used
        if remaining <= 0:
            break
        content = str(hit["content"])
        if len(content) > remaining:
            content = content[:remaining]
        used += len(content)
        item = {
            "source_id": f"S{len(evidence) + 1}",
            "document_name": hit["document_name"],
            "document_id": hit["document_id"],
            "segment_id": hit["segment_id"],
            "score": round(float(hit["score"]), 4),
            "content": content,
        }
        if hit.get("bypass"):
            item["bypass"] = True
        if hit.get("section"):
            item["section"] = hit["section"]
        evidence.append(item)
    return evidence
