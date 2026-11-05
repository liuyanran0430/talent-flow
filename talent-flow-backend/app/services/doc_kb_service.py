"""制度知识库构建服务：预处理、切分、入库与索引维护。

MySQL 为唯一事实源，向量库与 BM25 索引为可随时重建的派生索引：
- 分段写入 kb_segments，同时同步到 kb_docs 向量集合与 BM25 索引；
- 任一索引环节失败只记录告警，不阻断 MySQL 落库；
- 制度更新统一走 scripts/build_doc_kb.py，不提供管理入口。
"""

import os
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.logging_config import BASE_DIR, get_logger
from ..models import KbDocument, KbSegment
from ..rag import get_vector_store
from ..rag.bm25 import get_doc_bm25

logger = get_logger("kb")

DOC_NAMESPACE = "kb_docs"

# 源文件 → 文档编号 / 名称 / 知识领域（新增制度按 DOC-005 递增）
DOCUMENT_REGISTRY: dict[str, dict[str, str]] = {
    "岗位能力标准.md": {
        "document_id": "DOC-001",
        "document_name": "岗位能力标准",
        "domain": "job_ability",
    },
    "招聘阶段规则.md": {
        "document_id": "DOC-002",
        "document_name": "招聘阶段规则",
        "domain": "process_rule",
    },
    "面试评价规范.md": {
        "document_id": "DOC-003",
        "document_name": "面试评价规范",
        "domain": "interview_eval",
    },
    "招聘业务FAQ.md": {
        "document_id": "DOC-004",
        "document_name": "招聘业务FAQ",
        "domain": "business_faq",
    },
}

_SENTENCE_END_RE = re.compile(r"(?<=[。？！；\n])")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)


def knowledge_dir() -> str:
    return os.path.join(BASE_DIR, settings.QA_KNOWLEDGE_DIR)


def load_source_documents() -> list[dict]:
    """读取源目录下已登记的制度文档。"""
    docs: list[dict] = []
    base = knowledge_dir()
    for filename, meta in DOCUMENT_REGISTRY.items():
        path = os.path.join(base, filename)
        if not os.path.isfile(path):
            logger.warning("制度文档缺失：%s", path)
            continue
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
        docs.append(
            {
                **meta,
                "file_name": filename,
                "file_path": os.path.relpath(path, BASE_DIR),
                "text": raw,
            }
        )
    return docs


def normalize_text(text: str) -> str:
    """统一换行、折叠空格/制表符、去除行首尾空白、折叠连续空行；保留 Markdown 结构符。"""
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _heading(line: str) -> tuple[int, str] | None:
    match = _HEADING_RE.match(line.strip())
    if not match:
        return None
    return len(match.group(1)), match.group(2).strip()


def _split_blocks(text: str) -> list[dict]:
    """按章节标题切分块：每个块 = 标题 + 其后的正文，天然保证 FAQ/表格/代码块不被拆行。"""
    paragraphs = [p for p in text.split(settings.QA_DOC_CHUNK_SEPARATOR) if p.strip()]
    blocks: list[dict] = []
    h1 = h2 = h3 = ""
    current_lines: list[str] = []
    current_section = ""

    def _section_path() -> str:
        if h2 or h1:
            base = h2 or h1
            return f"{base} / {h3}" if h3 else base
        return h3

    def _flush() -> None:
        nonlocal current_lines
        if current_lines:
            blocks.append(
                {"content": settings.QA_DOC_CHUNK_SEPARATOR.join(current_lines), "section": current_section}
            )
            current_lines = []

    for paragraph in paragraphs:
        heading = _heading(paragraph.split("\n", 1)[0])
        if heading:
            _flush()
            level, title = heading
            if level == 1:
                h1, h2, h3 = title, "", ""
            elif level == 2:
                h2, h3 = title, ""
            else:
                h3 = title
            current_section = _section_path()
            current_lines = [paragraph]
        else:
            current_lines.append(paragraph)
    _flush()
    return blocks


def _is_table(content: str) -> bool:
    return sum(1 for line in content.split("\n") if line.strip().startswith("|")) >= 2


def _is_heading_only(content: str) -> bool:
    lines = [line for line in content.split("\n") if line.strip()]
    return len(lines) == 1 and _heading(lines[0]) is not None


def _is_faq(content: str) -> bool:
    first = content.strip().split("\n", 1)[0]
    return bool(re.match(r"^#{2,6}\s*(Q\s*\d*[：:.、]?)", first))


def _is_code(content: str) -> bool:
    return "```" in content


def _split_long_text(text: str, max_chars: int, overlap: int) -> list[str]:
    """按句子边界切分超长文本，相邻块保留重叠并对齐到句子起点。"""
    parts = [p for p in _SENTENCE_END_RE.split(text) if p]
    chunks: list[str] = []
    current = ""
    for part in parts:
        if len(current) + len(part) <= max_chars:
            current += part
            continue
        if current:
            chunks.append(current)
            current = ""
        while len(part) > max_chars:
            chunks.append(part[:max_chars])
            part = part[max_chars:]
        current = part
    if current:
        chunks.append(current)

    if overlap <= 0 or len(chunks) <= 1:
        return chunks
    result = [chunks[0]]
    for i in range(1, len(chunks)):
        prefix = chunks[i - 1][-overlap:]
        # 对齐到句子起点，避免半句截断
        match = re.search(r"[。？！；]", prefix)
        if match:
            prefix = prefix[match.end():]
        result.append((prefix + chunks[i]).strip())
    return result


def chunk_document(
    text: str,
    *,
    document_id: str,
    document_name: str,
    domain: str,
    version: str = "1.0",
    status: str = "current",
) -> list[dict]:
    """预处理 + 切分 + 生成元数据，返回分段列表（chunk_no 从 1 起）。"""
    normalized = normalize_text(text)
    if not normalized:
        return []

    max_chars = settings.QA_DOC_CHUNK_MAX_CHARS
    overlap = settings.QA_DOC_CHUNK_OVERLAP
    min_chars = settings.QA_DOC_MIN_CHUNK_CHARS

    raw_chunks: list[dict] = []
    for block in _split_blocks(normalized):
        content = block["content"].strip()
        if not content or _is_heading_only(content):
            # 纯标题块没有独立语义，章节路径已写入子块元数据，直接跳过
            continue
        if _is_faq(content):
            chunk_type = "faq"
        elif _is_table(content):
            chunk_type = "table"
        else:
            chunk_type = "text"

        # 表格/FAQ/代码块整块保留，避免拆行破坏表头字段对应或问答语义
        keep_whole = chunk_type in ("table", "faq") or _is_code(content)
        if keep_whole:
            raw_chunks.append({"content": content, "section": block["section"], "type": chunk_type})
            continue
        if len(content) <= max_chars:
            raw_chunks.append({"content": content, "section": block["section"], "type": chunk_type})
            continue
        for piece in _split_long_text(content, max_chars, overlap):
            raw_chunks.append({"content": piece, "section": block["section"], "type": chunk_type})

    # 过短块与相邻同章节块合并，减少碎片化召回噪声（FAQ 保持独立）
    merged: list[dict] = []
    for chunk in raw_chunks:
        if (
            merged
            and chunk["type"] != "faq"
            and merged[-1]["type"] != "faq"
            and chunk["section"] == merged[-1]["section"]
            and len(chunk["content"]) < min_chars
            and len(merged[-1]["content"]) + len(chunk["content"]) + 2 <= max_chars
        ):
            merged[-1]["content"] = f"{merged[-1]['content']}\n\n{chunk['content']}"
            continue
        merged.append(chunk)

    segments: list[dict] = []
    for index, chunk in enumerate(merged, start=1):
        segments.append(
            {
                "document_id": document_id,
                "document_name": document_name,
                "segment_id": f"{document_id}-S{index:03d}",
                "chunk_no": index,
                "section": chunk["section"],
                "content": chunk["content"],
                "char_count": len(chunk["content"]),
                "type": chunk["type"],
                "domain": domain,
                "version": version,
                "status": status,
            }
        )
    return segments


def segment_metadata(segment: dict) -> dict:
    """向量库 metadata：全部为标量值。"""
    return {
        "document_id": segment["document_id"],
        "document_name": segment["document_name"],
        "segment_id": segment["segment_id"],
        "chunk_no": int(segment["chunk_no"]),
        "domain": segment["domain"],
        "section": segment.get("section") or "",
        "type": segment["type"],
        "version": segment["version"],
        "status": segment["status"],
    }


def index_segments(segments: list[dict], *, reset: bool = False) -> None:
    """同步写入向量库与 BM25；任一失败只告警，检索侧自动降级。"""
    store = get_vector_store()
    if reset:
        try:
            reset_fn = getattr(store, "reset", None)
            if callable(reset_fn):
                reset_fn(DOC_NAMESPACE)
        except Exception as e:
            logger.warning("制度向量集合清理失败：%s", e)
    try:
        store.upsert_many(
            DOC_NAMESPACE,
            [
                {
                    "doc_id": seg["segment_id"],
                    "text": seg["content"],
                    "metadata": segment_metadata(seg),
                }
                for seg in segments
            ],
        )
    except Exception as e:
        logger.warning("制度向量写入失败，仅保留 BM25 索引：%s", e)

    try:
        index = get_doc_bm25()
        if reset:
            index.rebuild([(seg["segment_id"], seg["content"]) for seg in segments])
        else:
            for seg in segments:
                index.upsert(seg["segment_id"], seg["content"])
    except Exception as e:
        logger.warning("制度 BM25 索引写入失败：%s", e)


def remove_segment_indexes(segment_ids: list[str]) -> None:
    store = get_vector_store()
    for segment_id in segment_ids:
        try:
            store.delete(DOC_NAMESPACE, segment_id)
        except Exception as e:
            logger.warning("制度向量删除失败 segment_id=%s：%s", segment_id, e)
    try:
        index = get_doc_bm25()
        for segment_id in segment_ids:
            index.delete(segment_id)
    except Exception as e:
        logger.warning("制度 BM25 删除失败：%s", e)


def build_documents(
    db: Session,
    *,
    only_document_id: str | None = None,
    dry_run: bool = False,
    version: str = "1.0",
) -> dict:
    """构建（全量或单文档）。dry_run 只返回切分统计，不落库、不写索引。"""
    docs = load_source_documents()
    if only_document_id:
        docs = [d for d in docs if d["document_id"] == only_document_id]
        if not docs:
            raise ValueError(f"未找到文档：{only_document_id}")

    prepared: list[dict] = []
    for doc in docs:
        segments = chunk_document(
            doc["text"],
            document_id=doc["document_id"],
            document_name=doc["document_name"],
            domain=doc["domain"],
            version=version,
        )
        prepared.append({**doc, "segments": segments})

    stats = {
        "documents": len(prepared),
        "segments": sum(len(p["segments"]) for p in prepared),
        "max_chars": max((s["char_count"] for p in prepared for s in p["segments"]), default=0),
        "min_chars": min((s["char_count"] for p in prepared for s in p["segments"]), default=0),
        "table_chunks": sum(
            1 for p in prepared for s in p["segments"] if s["type"] == "table"
        ),
        "details": [
            {
                "document_id": p["document_id"],
                "document_name": p["document_name"],
                "chunks": len(p["segments"]),
            }
            for p in prepared
        ],
    }
    if dry_run:
        return stats

    stale_ids: list[str] = []
    all_segments: list[dict] = []
    for item in prepared:
        doc_id = item["document_id"]
        record = (
            db.execute(select(KbDocument).where(KbDocument.document_id == doc_id))
            .scalars()
            .first()
        )
        if not record:
            record = KbDocument(document_id=doc_id)
            db.add(record)
        record.document_name = item["document_name"]
        record.domain = item["domain"]
        record.file_path = item.get("file_path")
        record.version = version
        record.status = "current"
        record.chunk_count = len(item["segments"])

        old_segments = (
            db.execute(select(KbSegment).where(KbSegment.document_id == doc_id))
            .scalars()
            .all()
        )
        stale_ids.extend(seg.segment_id for seg in old_segments)
        db.query(KbSegment).filter(KbSegment.document_id == doc_id).delete()
        for segment in item["segments"]:
            db.add(
                KbSegment(
                    document_id=doc_id,
                    segment_id=segment["segment_id"],
                    chunk_no=segment["chunk_no"],
                    section=segment.get("section"),
                    content=segment["content"],
                    char_count=segment["char_count"],
                    type=segment["type"],
                    version=segment["version"],
                    status="current",
                )
            )
        all_segments.extend(item["segments"])

    db.flush()
    reset = only_document_id is None
    index_segments(all_segments, reset=reset)
    if not reset:
        # 单文档重建：清理不在新集合中的旧编号，避免残留脏召回
        new_ids = {s["segment_id"] for s in all_segments}
        remove_segment_indexes([sid for sid in stale_ids if sid not in new_ids])
    db.commit()
    logger.info(
        "制度知识库构建完成 documents=%s segments=%s", stats["documents"], stats["segments"]
    )
    return stats


def set_document_status(db: Session, document_id: str, status: str) -> dict:
    """切换文档状态：archived 从索引移除；current 重新按源文件构建。"""
    if status == "archived":
        record = (
            db.execute(select(KbDocument).where(KbDocument.document_id == document_id))
            .scalars()
            .first()
        )
        if not record:
            raise ValueError(f"未找到文档：{document_id}")
        segments = (
            db.execute(select(KbSegment).where(KbSegment.document_id == document_id))
            .scalars()
            .all()
        )
        record.status = "archived"
        for segment in segments:
            segment.status = "archived"
        db.commit()
        remove_segment_indexes([segment.segment_id for segment in segments])
        return {"document_id": document_id, "status": "archived", "chunks": len(segments)}
    if status == "current":
        return build_documents(db, only_document_id=document_id)
    raise ValueError(f"非法状态：{status}")


def list_documents(db: Session) -> list[dict]:
    records = db.execute(select(KbDocument).order_by(KbDocument.document_id)).scalars().all()
    return [
        {
            "document_id": r.document_id,
            "document_name": r.document_name,
            "domain": r.domain,
            "version": r.version,
            "status": r.status,
            "chunk_count": r.chunk_count,
            "updated_at": r.updated_at,
        }
        for r in records
    ]


def rebuild_doc_bm25_from_db(db: Session) -> int:
    """应用启动时从 MySQL 构建制度 BM25 索引，失败只告警不阻断。"""
    rows = (
        db.execute(
            select(KbSegment)
            .where(KbSegment.status == "current")
            .order_by(KbSegment.segment_id)
        )
        .scalars()
        .all()
    )
    current_ids = {
        r.document_id
        for r in db.execute(select(KbDocument).where(KbDocument.status == "current"))
        .scalars()
        .all()
    }
    docs = [(s.segment_id, s.content) for s in rows if s.document_id in current_ids]
    get_doc_bm25().rebuild(docs)
    return len(docs)
