"""招聘知识问答：切分、分类、检索、证据、校验、岗位分支与接口。"""

import json
from types import SimpleNamespace

import pytest

import app.services.doc_retriever as doc_retriever
import app.services.qa_service as qa_service
from app.core.config import settings
from app.models import Department, Job, KbDocument, KbSegment, RequirementItem
from app.services.doc_kb_service import chunk_document, normalize_text
from app.services.doc_retriever import build_evidence, retrieve_doc_segments
from app.services.job_profile import job_evidence, job_profile, resolve_job_target
from app.services.qa_classifier import (
    AMBIGUOUS,
    BUSINESS_FAQ,
    JOB_ABILITY,
    OUT_OF_SCOPE,
    PROCESS_RULE,
    normalize_category,
)
from app.services.qa_service import (
    FALLBACK_ANSWER,
    OUT_OF_SCOPE_ANSWER,
    parse_and_validate,
)


# ---------- 切分 ----------

def test_normalize_text_collapses_spaces_and_blank_lines():
    assert normalize_text("a\r\n\r\n\r\nb  \t c") == "a\n\nb c"


def test_chunk_document_skips_heading_only_and_keeps_table_whole():
    text = """# 测试制度

## 一、候选人状态机

### 1.1 pending
pending 表示待解析，候选人刚入库尚未开始解析，需要在 24 小时内完成处理。

## 二、状态表格
| 状态 | 含义 |
| --- | --- |
| review | 待复核 |
| finish | 已确认 |
"""
    segments = chunk_document(
        text, document_id="DOC-T", document_name="测试制度", domain="process_rule"
    )
    assert len(segments) >= 2
    assert [s["segment_id"] for s in segments] == [
        f"DOC-T-S{i:03d}" for i in range(1, len(segments) + 1)
    ]
    assert [s["chunk_no"] for s in segments] == list(range(1, len(segments) + 1))
    # 纯标题块被跳过
    for segment in segments:
        assert segment["content"].strip() != "## 一、候选人状态机"
        assert segment["content"].strip() != "# 测试制度"
    # 表格整块保留，不拆行
    table = next(s for s in segments if s["type"] == "table")
    assert "| review | 待复核 |" in table["content"]
    assert "| finish | 已确认 |" in table["content"]


def test_chunk_document_keeps_faq_separate_and_labels_section():
    text = """## 一、FAQ

### Q1：pending 是什么意思？
pending 表示待解析。

### Q2：review 是什么意思？
review 表示待 HR 复核。
"""
    segments = chunk_document(
        text, document_id="DOC-F", document_name="FAQ", domain="business_faq"
    )
    assert len(segments) == 2
    assert all(s["type"] == "faq" for s in segments)
    assert segments[0]["section"].startswith("一、FAQ")
    assert "pending 表示待解析" in segments[0]["content"]


def test_chunk_document_splits_long_text_with_overlap():
    sentence = "这是一条用于验证切分边界的制度说明，内容需要足够长才能触发二次切分。"
    text = "## 长文\n" + sentence * 30
    segments = chunk_document(
        text, document_id="DOC-L", document_name="长文", domain="process_rule"
    )
    assert len(segments) > 1
    max_chars = settings.QA_DOC_CHUNK_MAX_CHARS
    assert all(s["char_count"] <= max_chars + settings.QA_DOC_CHUNK_OVERLAP for s in segments)


# ---------- 分类器 ----------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("job_ability", "job_ability"),
        ("  process_rule  ", "process_rule"),
        ("`business_faq`", "business_faq"),
        ("岗位能力标准", "job_ability"),
        ("面试评价规范", "interview_eval"),
        ("招聘阶段规则", "process_rule"),
        ("无关问题", "out_of_scope"),
        ("无法判断", None),
        ("", None),
    ],
)
def test_normalize_category(raw, expected):
    assert normalize_category(raw) == expected


# ---------- 检索 ----------

def _seed_doc(db, *, domain="process_rule", segment_status="current", doc_status="current"):
    db.add(
        KbDocument(
            document_id="DOC-T",
            document_name="测试制度",
            domain=domain,
            status=doc_status,
            chunk_count=2,
        )
    )
    db.add(
        KbSegment(
            document_id="DOC-T",
            segment_id="DOC-T-S001",
            chunk_no=1,
            content="pending 状态表示待解析。",
            char_count=14,
            type="text",
            status=segment_status,
        )
    )
    db.add(
        KbSegment(
            document_id="DOC-T",
            segment_id="DOC-T-S002",
            chunk_no=2,
            content="review 状态表示待复核。",
            char_count=14,
            type="text",
            status=segment_status,
        )
    )
    db.commit()


def test_retrieve_doc_segments_fuses_two_paths(db, monkeypatch):
    _seed_doc(db)
    monkeypatch.setattr(
        doc_retriever, "_vector_search", lambda query, pool, domain: [{"doc_id": "DOC-T-S001", "score": 0.9}]
    )
    monkeypatch.setattr(
        doc_retriever, "bm25_search_docs", lambda query, top_k: [{"doc_id": "DOC-T-S001", "score": 0.8}]
    )
    hits = retrieve_doc_segments(db, "pending 是什么", PROCESS_RULE)
    assert hits and hits[0]["segment_id"] == "DOC-T-S001"
    assert "bypass" not in hits[0]
    assert hits[0]["score"] == pytest.approx(0.945, abs=0.01)


def test_retrieve_doc_segments_single_path_bypass(db, monkeypatch):
    _seed_doc(db)
    monkeypatch.setattr(
        doc_retriever, "_vector_search", lambda query, pool, domain: [{"doc_id": "DOC-T-S001", "score": 0.8}]
    )
    monkeypatch.setattr(doc_retriever, "bm25_search_docs", lambda query, top_k: [])
    hits = retrieve_doc_segments(db, "pending 是什么", PROCESS_RULE)
    assert len(hits) == 1
    assert hits[0]["bypass"] is True


def test_retrieve_doc_segments_drops_low_score(db, monkeypatch):
    _seed_doc(db)
    monkeypatch.setattr(
        doc_retriever, "_vector_search", lambda query, pool, domain: [{"doc_id": "DOC-T-S001", "score": 0.5}]
    )
    monkeypatch.setattr(doc_retriever, "bm25_search_docs", lambda query, top_k: [])
    assert retrieve_doc_segments(db, "pending 是什么", PROCESS_RULE) == []


def test_retrieve_doc_segments_filters_archived(db, monkeypatch):
    _seed_doc(db, domain="process_rule", segment_status="archived")
    monkeypatch.setattr(
        doc_retriever, "_vector_search", lambda query, pool, domain: [{"doc_id": "DOC-T-S001", "score": 1.0}]
    )
    monkeypatch.setattr(doc_retriever, "bm25_search_docs", lambda query, top_k: [])
    assert retrieve_doc_segments(db, "pending 是什么", PROCESS_RULE) == []


def test_retrieve_doc_segments_filters_domain(db, monkeypatch):
    _seed_doc(db, domain="process_rule")
    monkeypatch.setattr(
        doc_retriever, "_vector_search", lambda query, pool, domain: [{"doc_id": "DOC-T-S001", "score": 1.0}]
    )
    monkeypatch.setattr(
        doc_retriever, "bm25_search_docs", lambda query, top_k: [{"doc_id": "DOC-T-S001", "score": 1.0}]
    )
    assert retrieve_doc_segments(db, "pending 是什么", "interview_eval") == []


def test_build_evidence_numbers_and_drops_missing_fields():
    hits = [
        {"document_name": "A", "document_id": "DOC-A", "segment_id": "A-S2", "score": 0.6, "content": "内容二"},
        {"document_name": "B", "document_id": "DOC-B", "segment_id": "B-S1", "score": 0.9, "content": "内容一"},
        {"document_name": None, "document_id": "DOC-C", "segment_id": "C-S1", "score": 0.8, "content": "内容三"},
    ]
    evidence = build_evidence(hits)
    assert [item["source_id"] for item in evidence] == ["S1", "S2"]
    assert [item["segment_id"] for item in evidence] == ["B-S1", "A-S2"]


def test_build_evidence_truncates_total_chars():
    hits = [
        {"document_name": "A", "document_id": "DOC-A", "segment_id": "A-S1", "score": 0.9, "content": "1234567890"},
        {"document_name": "B", "document_id": "DOC-B", "segment_id": "B-S1", "score": 0.8, "content": "abcdefghij"},
    ]
    evidence = build_evidence(hits, max_chars=12)
    assert len(evidence) == 2
    assert evidence[0]["content"] == "1234567890"
    assert evidence[1]["content"] == "ab"
    assert build_evidence(hits, max_chars=0) == []


# ---------- 回答校验 ----------

def _evidence():
    return [
        {
            "source_id": "S1",
            "document_name": "招聘阶段规则",
            "document_id": "DOC-002",
            "segment_id": "DOC-002-S001",
            "score": 0.8,
            "content": "pending 表示待解析，review 表示待复核，需在 3 个工作日内处理。",
        },
        {
            "source_id": "S2",
            "document_name": "招聘业务FAQ",
            "document_id": "DOC-004",
            "segment_id": "DOC-004-S001",
            "score": 0.7,
            "content": "简历解析失败时状态保持为 review，等待人工复核。",
        },
    ]


def _payload(answer, answerable=True, used=("S1",)):
    return json.dumps(
        {"answer": answer, "answerable": answerable, "used_source_ids": list(used)},
        ensure_ascii=False,
    )


def test_parse_and_validate_passes_grounded_answer():
    result = parse_and_validate(_payload("pending 表示待解析（S1）。"), _evidence(), "pending 是什么？")
    assert result is not None
    assert result["answerable"] is True
    assert result["grounded"] is True
    assert result["used_source_ids"] == ["S1"]
    assert result["citations"][0]["segment_id"] == "DOC-002-S001"


def test_parse_and_validate_rejects_invalid_json_and_short_answer():
    assert parse_and_validate("不是 JSON", _evidence(), "问题") is None
    assert parse_and_validate(_payload("太短（S1）"), _evidence(), "问题") is None


def test_parse_and_validate_rejects_citation_mismatch_and_out_of_range():
    # V3：used_source_ids 与答案中的编号不一致
    assert parse_and_validate(_payload("结论没有编号。", used=["S1"]), _evidence(), "问题") is None
    # V4：引用越界
    assert parse_and_validate(_payload("结论有编号（S3）。", used=["S3"]), _evidence(), "问题") is None


def test_parse_and_validate_normalizes_segment_id_citations():
    raw = json.dumps(
        {
            "answer": "pending 表示待解析（DOC-002-S001）。",
            "answerable": True,
            "used_source_ids": ["DOC-002-S001"],
        },
        ensure_ascii=False,
    )
    result = parse_and_validate(raw, _evidence(), "pending 是什么？")
    assert result is not None
    assert result["used_source_ids"] == ["S1"]
    assert "（S1）" in result["answer"]


def test_parse_and_validate_unanswerable_requires_explanation():
    assert parse_and_validate(_payload("不知道", answerable=False, used=[]), _evidence(), "问题") is None
    result = parse_and_validate(_payload("资料未提及相关内容。", answerable=False, used=[]), _evidence(), "问题")
    assert result is not None
    assert result["answerable"] is False
    assert result["used_source_ids"] == []


def test_parse_and_validate_truncates_and_keeps_citation_ids(monkeypatch):
    monkeypatch.setattr(settings, "QA_ANSWER_MAX_CHARS", 40)
    answer = "第一条结论成立（S1）。" + "填充内容" * 12 + "第二条结论成立（S2）。"
    result = parse_and_validate(_payload(answer, used=["S1", "S2"]), _evidence(), "问题")
    assert result is not None
    assert len(result["answer"]) <= 60
    assert "引用：S2" in result["answer"]
    assert set(result["used_source_ids"]) == {"S1", "S2"}


def test_parse_and_validate_flags_ungrounded_numbers_and_common_sense():
    result = parse_and_validate(
        _payload("通常需要在 5 个工作日内完成（S1）。"), _evidence(), "多久完成？"
    )
    assert result is not None
    assert result["grounded"] is False
    assert "非制度内容" in result["notice"]
    assert "制度性描述" in result["notice"]


def test_parse_and_validate_multi_question_partial_notice():
    result = parse_and_validate(
        _payload("pending 表示待解析（S1）。"), _evidence(), "pending 是什么？review 是什么？"
    )
    assert result is not None
    assert "部分内容资料未覆盖" in result["answer"]
    assert "部分内容资料未覆盖" in result["notice"]


# ---------- 岗位分支 ----------

def _seed_jobs(db):
    tech = Department(name="技术部")
    data = Department(name="数据部")
    db.add_all([tech, data])
    db.commit()
    job = Job(name="大模型应用工程师", department_id=tech.id, status="open")
    db.add(job)
    db.commit()
    db.add(RequirementItem(job_id=job.id, name="RAG 原理", type="必须", importance="高", standard="能说明检索增强流程"))
    db.add(RequirementItem(job_id=job.id, name="Python", type="加分", importance="中", standard=None))
    db.commit()
    return job.id


def test_job_evidence_only_uses_requirement_items(db):
    job_id = _seed_jobs(db)
    profile = job_profile(db, {"job_id": job_id, "department_name": "技术部", "job_name": "大模型应用工程师"})
    evidence = job_evidence(profile)
    assert len(evidence) == 2
    assert evidence[0]["document_id"] == f"JOB-{job_id}"
    assert evidence[0]["segment_id"].startswith("REQ-")
    assert evidence[0]["content"].startswith("RAG 原理｜类型：必须｜重要度：高")
    # 无判定标准的要求项显式标注缺失，不引用 kb_standards
    missing = next(item for item in evidence if "Python" in item["content"])
    assert "判定标准：未配置" in missing["content"]
    assert missing["missing_standard"] is True
    assert all("standard_id" not in item for item in evidence)


def test_resolve_job_target_specific_by_department_and_name(db):
    _seed_jobs(db)
    target = resolve_job_target(db, "技术部大模型应用工程师需要什么能力？")
    assert target["status"] == "specific"
    assert target["job"]["job_name"] == "大模型应用工程师"


def test_resolve_job_target_department_only_and_pronoun(db):
    _seed_jobs(db)
    assert resolve_job_target(db, "技术部需要哪些能力？")["status"] == "department_only"

    target = resolve_job_target(db, "这个岗位需要什么能力？")
    assert target["status"] == "ambiguous"
    assert len(target["candidates"]) == 1
    assert target["candidates"][0]["job_name"] == "大模型应用工程师"

    target = resolve_job_target(db, "岗位要求项有哪些？")
    assert target["status"] == "ambiguous"
    assert target["candidates"]

    assert resolve_job_target(db, "RAG 原理的判定口径是什么？")["status"] == "none"


def test_resolve_job_target_standard_question_does_not_ask_for_job(db):
    """问某项能力的判定标准不应追问岗位；真正的岗位追问仍然保留。"""
    _seed_jobs(db)
    assert resolve_job_target(db, "RAG 判定标准是什么？")["status"] == "none"
    assert resolve_job_target(db, "岗位要求 RAG 的判定标准是什么？")["status"] == "none"
    target = resolve_job_target(db, "这个岗位要求项有哪些？")
    assert target["status"] == "ambiguous"
    assert target["candidates"]


def test_resolve_job_target_duplicate_name_is_ambiguous(db):
    _seed_jobs(db)
    data = db.query(Department).filter(Department.name == "数据部").one()
    db.add(Job(name="大模型应用工程师", department_id=data.id, status="open"))
    db.commit()
    target = resolve_job_target(db, "大模型应用工程师需要什么能力？")
    assert target["status"] == "ambiguous"
    assert len(target["candidates"]) == 2


def test_resolve_job_target_pending_choice_with_shared_department(db):
    _seed_jobs(db)
    tech = db.query(Department).filter(Department.name == "技术部").one()
    db.add(Job(name="AI算法工程师", department_id=tech.id, status="open"))
    db.commit()
    pending = {
        "type": "job_clarify",
        "question": "岗位要求项有哪些",
        "candidates": [
            {"job_id": 1, "department_name": "技术部", "job_name": "大模型应用工程师"},
            {"job_id": 2, "department_name": "技术部", "job_name": "AI算法工程师"},
        ],
    }
    # 部门名被两个候选共享，但用户同时给出了岗位名，必须直接确定为具体岗位
    target = resolve_job_target(db, "技术部/大模型应用工程师", pending)
    assert target["status"] == "specific"
    assert target["job"]["job_name"] == "大模型应用工程师"
    # 只给部门名时仍需追问
    assert resolve_job_target(db, "技术部", pending)["status"] == "ambiguous"


# ---------- 问答编排 ----------

def test_answer_question_out_of_scope(monkeypatch):
    monkeypatch.setattr(qa_service, "classify_question", lambda *a, **k: OUT_OF_SCOPE)
    result = qa_service.answer_question(None, "今天天气怎么样？")
    assert result["category"] == OUT_OF_SCOPE
    assert result["hit"] is False
    assert result["answer"]["answer"] == OUT_OF_SCOPE_ANSWER
    assert result["answer"]["citations"] == []


def test_answer_question_ambiguous_clarify(monkeypatch):
    monkeypatch.setattr(qa_service, "classify_question", lambda *a, **k: AMBIGUOUS)
    result = qa_service.answer_question(None, "这个怎么弄？")
    assert result["category"] == AMBIGUOUS
    assert result["hit"] is False
    assert "请说明具体制度或事项" in result["answer"]["answer"]


def test_answer_question_job_hint_walks_job_clarify(db, monkeypatch):
    _seed_jobs(db)
    monkeypatch.setattr(qa_service, "classify_question", lambda *a, **k: AMBIGUOUS)
    result = qa_service.answer_question(db, "这个岗位要求项有哪些？")
    assert result["category"] == JOB_ABILITY
    assert result["hit"] is False
    assert "请说明具体岗位" in result["answer"]["answer"]
    assert "可选岗位：技术部 / 大模型应用工程师" in result["answer"]["answer"]
    assert result["pending_intent"]["type"] == "job_clarify"
    assert result["pending_intent"]["candidates"][0]["job_name"] == "大模型应用工程师"


def test_answer_question_standard_hint_routes_to_generic_kb(db, monkeypatch):
    """分类器误判 ambiguous 时，标准类问题强制走 job_ability 通用检索，不追问岗位。"""
    monkeypatch.setattr(qa_service, "classify_question", lambda *a, **k: AMBIGUOUS)
    captured = {}

    def fake_retrieve(session, query, domain=None):
        captured["domain"] = domain
        return [
            {
                "segment_id": "DOC-001-S001",
                "document_id": "DOC-001",
                "document_name": "岗位能力标准",
                "domain": "job_ability",
                "section": "二、通用素质标准 / RAG",
                "content": "RAG 原理的判定标准是掌握检索增强生成的完整链路。",
                "type": "text",
                "score": 0.9,
            }
        ]

    monkeypatch.setattr(qa_service, "retrieve_doc_segments", fake_retrieve)
    fake = SimpleNamespace(
        chat_model=SimpleNamespace(
            invoke=lambda messages: SimpleNamespace(
                content=_payload("RAG 原理的判定标准是掌握检索增强生成的完整链路（S1）。")
            )
        )
    )
    monkeypatch.setattr(qa_service, "get_model_client", lambda: fake)
    result = qa_service.answer_question(db, "RAG 判定标准是什么？")
    assert result["category"] == JOB_ABILITY
    assert captured["domain"] == JOB_ABILITY
    assert result["hit"] is True
    assert result["answer"]["citations"][0]["document_id"] == "DOC-001"


def test_answer_question_empty_evidence_returns_fallback(db, monkeypatch):
    monkeypatch.setattr(qa_service, "classify_question", lambda *a, **k: BUSINESS_FAQ)
    monkeypatch.setattr(qa_service, "retrieve_doc_segments", lambda *a, **k: [])
    result = qa_service.answer_question(db, "简历解析失败怎么办？")
    assert result["hit"] is False
    assert result["answer"]["answer"] == FALLBACK_ANSWER


def test_answer_question_generates_with_mocked_llm(db, monkeypatch):
    monkeypatch.setattr(qa_service, "classify_question", lambda *a, **k: PROCESS_RULE)
    monkeypatch.setattr(
        qa_service,
        "retrieve_doc_segments",
        lambda *a, **k: [
            {
                "segment_id": "DOC-002-S001",
                "document_id": "DOC-002",
                "document_name": "招聘阶段规则",
                "domain": "process_rule",
                "section": "一、候选人状态机",
                "content": "pending 表示待解析。",
                "type": "text",
                "score": 0.9,
            }
        ],
    )
    fake = SimpleNamespace(
        chat_model=SimpleNamespace(
            invoke=lambda messages: SimpleNamespace(
                content=_payload("pending 表示待解析（S1）。")
            )
        )
    )
    monkeypatch.setattr(qa_service, "get_model_client", lambda: fake)
    result = qa_service.answer_question(db, "pending 是什么意思？")
    assert result["hit"] is True
    assert result["answer"]["used_source_ids"] == ["S1"]
    assert result["category"] == PROCESS_RULE


def test_answer_question_job_branch_returns_job_profile(db, monkeypatch):
    job_id = _seed_jobs(db)
    monkeypatch.setattr(qa_service, "classify_question", lambda *a, **k: JOB_ABILITY)
    fake = SimpleNamespace(
        chat_model=SimpleNamespace(
            invoke=lambda messages: SimpleNamespace(
                content=_payload("该岗位要求掌握 RAG 原理（S1）。")
            )
        )
    )
    monkeypatch.setattr(qa_service, "get_model_client", lambda: fake)
    result = qa_service.answer_question(db, "技术部大模型应用工程师需要什么能力？")
    assert result["job"]["job_id"] == job_id
    assert result["hit"] is True
    assert result["answer"]["citations"][0]["document_id"] == f"JOB-{job_id}"


def test_answer_question_disabled_returns_maintenance(db, monkeypatch):
    monkeypatch.setattr(settings, "QA_ENABLED", False)
    result = qa_service.answer_question(db, "任何问题")
    assert result["degraded"] is True
    assert "维护中" in result["answer"]["answer"]


# ---------- 接口 ----------

def test_qa_ask_api_creates_async_task(client, monkeypatch):
    monkeypatch.setattr(qa_service, "classify_question", lambda *a, **k: OUT_OF_SCOPE)
    response = client.post(
        "/qa/ask",
        json={"question": "今天天气怎么样？", "session_id": "test-session"},
        headers={"X-Session-ID": "test-session"},
    )
    assert response.status_code == 200
    request_id = response.json()["data"]["request_id"]
    assert request_id

    task = client.get(f"/tasks/{request_id}")
    assert task.status_code == 200
    data = task.json()["data"]
    assert data["status"] == "success"
    assert data["result"]["category"] == OUT_OF_SCOPE
    assert data["result"]["session_id"] == "test-session"


def test_qa_ask_api_rejects_empty_question(client):
    response = client.post("/qa/ask", json={"question": ""})
    assert response.status_code == 422


# ---------- 历史摘要压缩 ----------

def _make_turns(n: int) -> list[dict]:
    return [{"question": f"问题{i}", "answer": f"回答{i}"} for i in range(1, n + 1)]


def test_history_context_keeps_recent_turns_verbatim_when_within_window():
    # 4 轮以内全部原文注入，不触发摘要
    ctx = qa_service._history_context(_make_turns(3))
    assert "问题1" in ctx and "回答3" in ctx
    assert "较早对话摘要" not in ctx


def test_history_context_summarizes_older_turns(monkeypatch):
    calls = {"count": 0}

    def _fake_summary(turns):
        calls["count"] += 1
        assert len(turns) == 2  # 6 轮 - 保留最近 4 轮 = 2 轮进入摘要
        return "用户此前在了解技术中心大模型应用工程师的任职要求"

    monkeypatch.setattr(qa_service, "_summarize_history", _fake_summary)
    ctx = qa_service._history_context(_make_turns(6))
    assert calls["count"] == 1
    assert "【较早对话摘要】" in ctx
    assert "技术中心大模型应用工程师" in ctx
    assert "问题1" not in ctx  # 最早轮次不再以原文出现
    assert "问题6" in ctx and "回答6" in ctx  # 最近轮次保留原文


def test_history_context_degrades_when_summary_fails(monkeypatch):
    def _boom(_turns):
        return None  # 摘要失败：降级为仅保留最近轮次

    monkeypatch.setattr(qa_service, "_summarize_history", _boom)
    ctx = qa_service._history_context(_make_turns(6))
    assert "较早对话摘要" not in ctx
    assert "问题1" not in ctx
    assert "问题6" in ctx


def test_history_context_truncates_to_max_turns(monkeypatch):
    captured = {}

    def _fake_summary(turns):
        captured["older"] = turns
        return "摘要"

    monkeypatch.setattr(qa_service, "_summarize_history", _fake_summary)
    ctx = qa_service._history_context(_make_turns(12))
    # 仅取最后 QA_MAX_HISTORY_TURNS 轮：摘要覆盖 8-4=4 轮，最早 4 轮直接丢弃
    assert len(captured["older"]) == settings.QA_MAX_HISTORY_TURNS - settings.QA_HISTORY_RECENT_TURNS
    assert "问题4" not in ctx  # 最后 8 轮为 5~12，第 4 轮及更早直接丢弃
    assert "问题5" in captured["older"][0]["question"]
    assert "问题12" in ctx


def test_summarize_history_success_and_failure(monkeypatch):
    class _Chat:
        def invoke(self, _messages):
            return SimpleNamespace(content="  用户已确定岗位是产品经理  ")

    monkeypatch.setattr(
        qa_service, "ModelClient", lambda **_kw: SimpleNamespace(chat_model=_Chat())
    )
    summary = qa_service._summarize_history(_make_turns(2))
    assert summary == "用户已确定岗位是产品经理"

    def _blocked(**_kw):
        raise RuntimeError("LLM 不可用")

    monkeypatch.setattr(qa_service, "ModelClient", _blocked)
    assert qa_service._summarize_history(_make_turns(2)) is None  # 异常降级为 None，不抛出
