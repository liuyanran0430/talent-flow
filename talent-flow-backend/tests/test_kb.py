"""岗位标准知识库用例：CRUD/发布、历史沉淀去重、检索降级与引用校验。"""

import json

from app.models import Job, KbStandard
from app.services import kb_service
from app.services.jd_parser import RequirementItemSpec, RequirementList, validate
from app.services.kb_service import retrieve_standards


def _create_job(db, description: str | None = None) -> int:
    job = Job(name="AI算法工程师", status="open", description=description)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job.id


def test_create_and_list_standard(client):
    r = client.post(
        "/kb/standards",
        json={
            "name": "Python",
            "category": "技能",
            "standard": "3 年以上 Python 开发经验，熟悉常用标准库",
            "required_evidence": "项目经历或代码仓库",
            "aliases": ["Python开发", "Python 基础"],
        },
    )
    assert r.status_code == 201
    data = r.json()["data"]
    assert data["code"].startswith("KB-")
    assert data["status"] == "draft"
    assert data["aliases"] == ["Python开发", "Python 基础"]

    r = client.get("/kb/standards", params={"q": "Python"})
    assert r.status_code == 200
    assert len(r.json()["data"]) == 1


def test_create_duplicate_name_rejected(client):
    payload = {"name": "Python", "standard": "3 年以上"}
    assert client.post("/kb/standards", json=payload).status_code == 201
    assert client.post("/kb/standards", json=payload).status_code == 400


def test_publish_sets_status(client, monkeypatch):
    """发布：状态置 published；向量化失败（未配 DashScope 密钥）只降级不影响发布。"""
    r = client.post("/kb/standards", json={"name": "Java", "standard": "5 年经验"})
    standard_id = r.json()["data"]["id"]

    r = client.post(f"/kb/standards/{standard_id}/publish")
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "published"


def test_import_from_requirements_skips_existing(client, db):
    job_id = _create_job(db)
    r = client.post(
        f"/requirements/{job_id}/items/batch",
        json={
            "items": [
                {"name": "Python", "type": "必须", "importance": "高", "standard": "3 年"},
                {"name": "沟通能力", "type": "加分", "importance": "中", "standard": "跨团队协作"},
            ]
        },
    )
    assert r.status_code == 200

    # 先准备一条同名标准，导入时应跳过
    client.post("/kb/standards", json={"name": "Python", "standard": "3 年"})

    r = client.post("/kb/import/requirements", json={"limit": 200})
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["created"] == 1  # 沟通能力
    assert body["skipped"] >= 1  # Python 已存在

    # 分类规则：软素质关键词命中
    items = client.get("/kb/standards", params={"q": "沟通"}).json()["data"]
    assert items[0]["category"] == "软素质"


def test_retrieve_standards_degrades_without_embedding_key(db):
    """未配置 EMBEDDING_API_KEY：检索返回空，调用方走纯 LLM，不抛异常。"""
    db.add(
        KbStandard(
            code="KB-TEST1",
            name="Python",
            category="技能",
            status="published",
            standard="3 年经验",
        )
    )
    db.commit()
    assert retrieve_standards(db, "Python 后端") == []


def test_retrieve_standards_filters_and_scores(db, monkeypatch):
    """检索成功：只返回已发布标准，score 达标才注入，并带出判定标准。"""
    published = KbStandard(code="KB-P1", name="Python", category="技能", status="published", standard="3 年经验")
    draft = KbStandard(code="KB-D1", name="Java", category="技能", status="draft", standard="5 年经验")
    db.add_all([published, draft])
    db.commit()

    class _FakeStore:
        def search(self, namespace, query, top_k=5):
            return [
                {"doc_id": str(published.id), "score": 0.9, "text": "", "metadata": {}},
                {"doc_id": str(draft.id), "score": 0.88, "text": "", "metadata": {}},
            ]

    monkeypatch.setattr(kb_service, "get_vector_store", lambda: _FakeStore())

    hits = retrieve_standards(db, "Python 后端开发")
    assert [h["id"] for h in hits] == [published.id]
    assert hits[0]["standard"] == "3 年经验"


def test_validate_drops_unknown_standard_id():
    """引用校验：模型编造的 standard_id 不在本次注入范围，必须剔除。"""
    result = RequirementList(
        items=[
            RequirementItemSpec(name="Python", type="必须", importance="高", standard="3 年", standard_id=1),
            RequirementItemSpec(name="Java", type="必须", importance="中", standard="2 年", standard_id=999),
        ]
    )
    out = validate(result, {1})
    data = json.loads(out)
    assert data["items"][0]["standard_id"] == 1
    assert data["items"][1]["standard_id"] is None


# ---------- BM25 + RRF + 混合检索 ----------

from app.rag.bm25 import BM25Index, tokenize  # noqa: E402
from app.services.kb_service import _rrf_fuse  # noqa: E402


def test_bm25_tokenize_chinese_and_english():
    tokens = tokenize("Python 开发经验")
    assert "python" in tokens
    assert "开发" in tokens
    assert "经验" in tokens


def test_bm25_search_ranks_exact_match_first():
    idx = BM25Index()
    idx.upsert("1", "Python 开发经验 5年以上")
    idx.upsert("2", "Java 后端开发 SpringBoot")
    idx.upsert("3", "RAG 检索增强 LangChain")
    results = idx.search("Python 开发", top_k=3)
    assert results[0]["doc_id"] == "1"
    assert results[0]["score"] == 1.0


def test_bm25_delete_and_rebuild():
    idx = BM25Index()
    idx.upsert("1", "Python 开发")
    idx.upsert("2", "Java 开发")
    assert len(idx.search("开发", top_k=10)) == 2
    idx.delete("1")
    results = idx.search("Python", top_k=10)
    assert all(r["doc_id"] != "1" for r in results)
    idx.rebuild([("1", "Python 开发"), ("2", "Java 开发")])
    assert len(idx.search("开发", top_k=10)) == 2


def test_rrf_fuse_combines_rankings():
    # doc "a" 在两路都排第 1，应得分最高
    rankings = [["a", "b", "c"], ["a", "c", "b"]]
    scores = _rrf_fuse(rankings, k=60)
    assert scores["a"] > scores["b"]
    assert scores["a"] > scores["c"]


def test_retrieve_standards_hybrid_uses_bm25(db, monkeypatch):
    """混合检索：向量路和 BM25 路都命中时，RRF 融合后取并集。"""
    published = KbStandard(code="KB-H1", name="Python", category="技能", status="published", standard="3 年经验")
    db.add(published)
    db.commit()

    # mock 向量路返回空，BM25 路命中
    class _FakeStore:
        def search(self, namespace, query, top_k=5):
            return []

    monkeypatch.setattr(kb_service, "get_vector_store", lambda: _FakeStore())
    # 手动写入 BM25 索引
    from app.rag.bm25 import get_standard_bm25
    get_standard_bm25().upsert(str(published.id), "Python 技能 3年经验")

    hits = retrieve_standards(db, "Python 开发")
    assert any(h["id"] == published.id for h in hits)


def test_retrieve_standards_vector_only_when_bm25_disabled(db, monkeypatch):
    """BM25 关闭时仅走向量路，不影响检索。"""
    published = KbStandard(code="KB-V1", name="Java", category="技能", status="published", standard="5 年经验")
    db.add(published)
    db.commit()

    class _FakeStore:
        def search(self, namespace, query, top_k=5):
            return [{"doc_id": str(published.id), "score": 0.95, "text": "", "metadata": {}}]

    monkeypatch.setattr(kb_service, "get_vector_store", lambda: _FakeStore())
    monkeypatch.setattr(kb_service.settings, "RAG_BM25_ENABLED", False)

    hits = retrieve_standards(db, "Java 开发")
    assert [h["id"] for h in hits] == [published.id]
