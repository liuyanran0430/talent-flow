"""岗位标准知识库服务：CRUD、发布/归档、历史沉淀与向量索引维护。

MySQL 为唯一事实源，向量库为派生索引：
- 发布时写入向量，归档/删除时移除向量；
- 向量化失败只记录告警，状态照常落库（检索侧自动降级），不阻断业务流程。
"""

import json
import uuid

from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.logging_config import get_logger
from ..models import KbStandard
from ..rag import get_vector_store
from ..repositories import KbStandardRepository
from ..schemas.kb import (
    KbImportRequest,
    KbImportResult,
    KbReindexResult,
    KbSearchHit,
    KbSearchResult,
    KbStandardCreate,
    KbStandardOut,
    KbStandardUpdate,
)

logger = get_logger("kb")

# 向量集合名：岗位标准条目（对应项目约定 kb_standards）
STANDARD_NAMESPACE = "kb_standards"

# 历史要求项沉淀时的分类规则（未命中统一归为「技能」）
_CATEGORY_RULES = (
    ("经验", ("经验", "年限", "年以上", "工作")),
    ("学历", ("学历", "本科", "硕士", "博士", "大专", "985", "211")),
    ("证书", ("证书", "认证", "执照", "CPA", "PMP")),
    ("软素质", ("沟通", "协作", "团队", "抗压", "责任心", "学习能力", "领导")),
)


class KbValidationError(Exception):
    """入参不合法（空名称、重复名称等）"""


def infer_category(name: str) -> str:
    for category, keywords in _CATEGORY_RULES:
        if any(k in name for k in keywords):
            return category
    return "技能"


def _aliases(standard: KbStandard) -> list[str]:
    if not standard.aliases:
        return []
    try:
        parsed = json.loads(standard.aliases)
        return parsed if isinstance(parsed, list) else []
    except ValueError:
        return []


def standard_to_text(standard: KbStandard) -> str:
    """拼接向量化文本：名称 + 别名 + 分类 + 判定标准 + 证据要求。"""
    parts = [
        standard.name,
        "、".join(_aliases(standard)),
        f"分类：{standard.category}",
        f"职级：{standard.level}",
        standard.standard or "",
        f"证据要求：{standard.required_evidence}" if standard.required_evidence else "",
    ]
    return "\n".join(p for p in parts if p)


def standard_to_metadata(standard: KbStandard) -> dict:
    return {
        "standard_id": standard.id,
        "code": standard.code,
        "name": standard.name,
        "category": standard.category,
        "level": standard.level,
        "status": standard.status,
        "version": standard.version,
        "aliases": "、".join(_aliases(standard)),
    }


def index_standard(standard: KbStandard) -> bool:
    """把单条已发布标准写入向量库；失败只告警，返回 False。"""
    try:
        get_vector_store().upsert(
            STANDARD_NAMESPACE,
            str(standard.id),
            standard_to_text(standard),
            standard_to_metadata(standard),
        )
        return True
    except Exception as e:
        logger.warning("岗位标准向量化失败 standard_id=%s error=%s", standard.id, e)
        return False


def remove_standard_from_index(standard_id: int) -> None:
    try:
        get_vector_store().delete(STANDARD_NAMESPACE, str(standard_id))
    except Exception as e:
        logger.warning("岗位标准向量删除失败 standard_id=%s error=%s", standard_id, e)


class KbStandardService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = KbStandardRepository(db)

    # ---------- 查询 ----------
    def list(
        self,
        query: str | None = None,
        category: str | None = None,
        status: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[KbStandardOut]:
        return [
            KbStandardOut.model_validate(s)
            for s in self.repo.list_by_filters(query, category, status, limit, offset)
        ]

    def get(self, standard_id: int) -> KbStandardOut | None:
        standard = self.repo.get(standard_id)
        return KbStandardOut.model_validate(standard) if standard else None

    # ---------- 写入 ----------
    def create(self, payload: KbStandardCreate) -> KbStandardOut:
        name = payload.name.strip()
        if not name:
            raise KbValidationError("标准名称不能为空")
        if self.repo.get_by_name(name):
            raise KbValidationError(f"标准名称已存在：{name}")
        code = (payload.code or "").strip() or f"KB-{uuid.uuid4().hex[:8].upper()}"
        if self.repo.get_by_code(code):
            raise KbValidationError(f"标准编码已存在：{code}")
        standard = KbStandard(
            code=code,
            name=name,
            category=payload.category,
            level=payload.level,
            type=payload.type,
            importance=payload.importance,
            standard=payload.standard,
            required_evidence=payload.required_evidence,
            negative_signals=payload.negative_signals,
            aliases=json.dumps(payload.aliases, ensure_ascii=False),
            job_family=payload.job_family,
            source=payload.source,
            status="draft",
        )
        self.repo.add(standard)
        self.repo.commit()
        self.repo.refresh(standard)
        return KbStandardOut.model_validate(standard)

    def update(self, standard_id: int, payload: KbStandardUpdate) -> KbStandardOut:
        standard = self.repo.get(standard_id)
        if not standard:
            raise KbValidationError("标准不存在")
        data = payload.model_dump(exclude_unset=True)
        if "name" in data:
            name = (data["name"] or "").strip()
            if not name:
                raise KbValidationError("标准名称不能为空")
            other = self.repo.get_by_name(name)
            if other and other.id != standard_id:
                raise KbValidationError(f"标准名称已存在：{name}")
            data["name"] = name
        if "aliases" in data:
            data["aliases"] = json.dumps(data["aliases"] or [], ensure_ascii=False)
        for key, value in data.items():
            setattr(standard, key, value)
        # 已发布标准内容变更视为新版本，重新向量化
        if standard.status == "published":
            standard.version += 1
            standard.embedding_model = settings.EMBEDDING_MODEL
        self.repo.commit()
        self.repo.refresh(standard)
        if standard.status == "published":
            index_standard(standard)
        return KbStandardOut.model_validate(standard)

    def publish(self, standard_id: int) -> KbStandardOut:
        standard = self.repo.get(standard_id)
        if not standard:
            raise KbValidationError("标准不存在")
        was_published = standard.status == "published"
        standard.status = "published"
        if was_published:
            standard.version += 1
        standard.embedding_model = settings.EMBEDDING_MODEL
        self.repo.commit()
        self.repo.refresh(standard)
        index_standard(standard)
        return KbStandardOut.model_validate(standard)

    def archive(self, standard_id: int) -> KbStandardOut:
        standard = self.repo.get(standard_id)
        if not standard:
            raise KbValidationError("标准不存在")
        standard.status = "archived"
        self.repo.commit()
        self.repo.refresh(standard)
        remove_standard_from_index(standard.id)
        return KbStandardOut.model_validate(standard)

    def delete(self, standard_id: int) -> None:
        standard = self.repo.get(standard_id)
        if not standard:
            raise KbValidationError("标准不存在")
        remove_standard_from_index(standard.id)
        self.repo.delete(standard)
        self.repo.commit()

    def import_from_requirements(self, payload: KbImportRequest) -> KbImportResult:
        """把历史要求项名称沉淀为标准草稿：已存在同名/别名的跳过，分类按规则推断。"""
        existing = self.repo.list_existing_names()
        created = skipped = 0
        for name in self.repo.list_requirement_names(payload.limit):
            name = (name or "").strip()
            if not name:
                continue
            if name in existing:
                skipped += 1
                continue
            standard = KbStandard(
                code=f"KB-{uuid.uuid4().hex[:8].upper()}",
                name=name,
                category=infer_category(name),
                standard=None,
                source="历史要求项",
                status="draft",
            )
            self.repo.add(standard)
            existing.add(name)
            created += 1
        self.repo.commit()
        return KbImportResult(created=created, skipped=skipped)

    # ---------- 索引 ----------
    def reindex(self) -> KbReindexResult:
        """全量重建：清空集合后把所有已发布标准重新向量化。"""
        standards = self.repo.list_published()
        if not settings.RAG_ENABLED:
            return KbReindexResult(total=len(standards), degraded=True)
        store = get_vector_store()
        try:
            reset = getattr(store, "reset", None)
            if callable(reset):
                reset(STANDARD_NAMESPACE)
            items = [
                {
                    "doc_id": str(s.id),
                    "text": standard_to_text(s),
                    "metadata": standard_to_metadata(s),
                }
                for s in standards
            ]
            store.upsert_many(STANDARD_NAMESPACE, items)
            for s in standards:
                s.embedding_model = settings.EMBEDDING_MODEL
            self.repo.commit()
            return KbReindexResult(total=len(standards), indexed=len(standards))
        except Exception as e:
            logger.warning("岗位标准全量重建失败：%s", e)
            return KbReindexResult(total=len(standards), failed=len(standards), degraded=True)

    # ---------- 检索 ----------
    def search(self, query: str, top_k: int = 5) -> KbSearchResult:
        query = (query or "").strip()
        if not query:
            return KbSearchResult(query=query)
        hits = retrieve_standards(self.db, query, top_k=top_k)
        return KbSearchResult(
            query=query,
            hits=[
                KbSearchHit(
                    standard_id=h["id"],
                    code=h["code"],
                    name=h["name"],
                    standard=h.get("standard"),
                    score=round(float(h.get("score") or 0), 4),
                )
                for h in hits
            ],
            degraded=not (settings.RAG_ENABLED and settings.EMBEDDING_API_KEY),
        )


def retrieve_standards(
    db: Session, query: str, top_k: int | None = None
) -> list[dict]:
    """检索已发布标准，返回 [{id, code, name, standard, required_evidence, score}]。

    任一环节失败（未配置密钥、向量库异常）都返回空列表并告警，调用方按纯 LLM 降级。
    """
    if not settings.RAG_ENABLED:
        return []
    top_k = top_k or settings.RAG_TOP_K
    if top_k <= 0:
        return []
    try:
        raw_hits = get_vector_store().search(STANDARD_NAMESPACE, query, top_k=top_k * 2)
    except Exception as e:
        logger.warning("岗位标准检索失败，降级为纯 LLM：%s", e)
        return []

    ids: list[int] = []
    for hit in raw_hits:
        try:
            ids.append(int(hit.get("doc_id")))
        except (TypeError, ValueError):
            continue
    if not ids:
        return []

    repo = KbStandardRepository(db)
    published = {s.id: s for s in repo.list_published_by_ids(ids)}
    query_lower = query.lower()
    hits: list[dict] = []
    for hit in raw_hits:
        try:
            standard_id = int(hit.get("doc_id"))
        except (TypeError, ValueError):
            continue
        standard = published.get(standard_id)
        if not standard:
            # 向量库残留（已归档/删除）不注入
            continue
        score = float(hit.get("score") or 0)
        # 名称/别名命中加权，弥补纯向量检索对专有名词不敏感：标准名出现在查询中即加权
        names = [standard.name, *_aliases(standard)]
        if any(name and name.lower() in query_lower for name in names):
            score = min(1.0, score + 0.1)
        if score < settings.RAG_MIN_SCORE:
            continue
        hits.append(
            {
                "id": standard.id,
                "code": standard.code,
                "name": standard.name,
                "standard": standard.standard,
                "required_evidence": standard.required_evidence,
                "score": score,
            }
        )
    hits.sort(key=lambda h: h["score"], reverse=True)
    return hits[:top_k]
