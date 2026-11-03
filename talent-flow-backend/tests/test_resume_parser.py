"""简历解析业务校验：优势必须带证据、建议项对齐（LLM 全部 mock）。"""

import json

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from app.services import resume_parser as rp
from app.services.resume_parser import (
    AnalysisPoint,
    BasicInfo,
    MatchSuggestion,
    ResumeParseResult,
    _validate,
    parse_resume,
)


def _result(advantages, risks=None, suggestions=None) -> ResumeParseResult:
    """用真实构造（非 model_construct）：证明空证据不会再让 pydantic 校验失败。"""
    return ResumeParseResult(
        basic=BasicInfo(),
        suggestions=suggestions or [],
        advantages=advantages,
        risks=risks or [],
    )


def test_validate_filters_advantages_without_evidence():
    """优势 evidence 为空 / 太短 / point 为空 → 一律剔除；有效优势保留。"""
    valid = "2019-2024 年负责 Python 后端开发"
    result = _result(
        [
            AnalysisPoint(point="5 年 Python 经验", evidence=valid),
            AnalysisPoint(point="沟通能力强", evidence=""),          # 空证据
            AnalysisPoint(point="文档能力", evidence="   "),         # 空白证据
            AnalysisPoint(point="会写测试", evidence="无"),          # 1 字 < 6
            AnalysisPoint(point="熟悉 K8s", evidence="abc"),        # 3 字 < 6
            AnalysisPoint(point="   ", evidence="六个字以上的证据内容"),  # 空 point
        ]
    )
    data = json.loads(_validate(result, ["Python 开发经验"]))
    assert data["advantages"] == [{"point": "5 年 Python 经验", "evidence": valid}]


def test_validate_keeps_risks_even_without_evidence():
    """风险证据较弱也保留（提醒 HR 核实），但 point 为空仍要剔除。"""
    result = _result(
        advantages=[],
        risks=[
            AnalysisPoint(point="缺乏团队管理经验", evidence=""),
            AnalysisPoint(point="  ", evidence="六年以上经验"),
        ],
    )
    data = json.loads(_validate(result, []))
    assert data["risks"] == [{"point": "缺乏团队管理经验", "evidence": ""}]


def test_validate_aligns_suggestions_with_requirement_names():
    """多余建议剔除、缺失建议补「证据不足」、顺序按输入要求项。"""
    result = _result(
        advantages=[],
        suggestions=[
            MatchSuggestion(name="Python 开发经验", suggestion="满足", evidence="5 年"),
            MatchSuggestion(name="LLM 微调经验", suggestion="满足", evidence="做过 SFT"),
            MatchSuggestion(name="不存在的项", suggestion="不满足", evidence="x"),
        ],
    )
    data = json.loads(_validate(result, ["Python 开发经验", "K8s"]))
    assert data["suggestions"] == [
        {"name": "Python 开发经验", "suggestion": "满足", "evidence": "5 年"},
        {"name": "K8s", "suggestion": "证据不足", "evidence": ""},
    ]


def test_parse_resume_with_fake_llm_filters_weak_advantages(monkeypatch, tmp_path):
    """走完整 chain（读取文件 → 假 LLM → parser → validate），验证业务过滤生效。"""
    resume = tmp_path / "resume.txt"
    resume.write_text("张三，2019-2024 年负责 Python 后端开发，熟练使用 SQL。", encoding="utf-8")

    payload = json.dumps({
        "basic": {"name": "张三", "phone": None, "email": None, "experience": "5 年"},
        "suggestions": [
            {"name": "Python 开发经验", "suggestion": "满足", "evidence": "负责 Python 后端开发"},
            {"name": "多余项", "suggestion": "满足", "evidence": "不该出现"},
        ],
        "advantages": [
            {"point": "5 年 Python 后端经验", "evidence": "2019-2024 年负责 Python 后端开发"},
            {"point": "沟通能力强", "evidence": ""},       # 空证据不再让 parser 抛错，由 _validate 剔除
            {"point": "文档能力", "evidence": "   "},
            {"point": "会写测试", "evidence": "无"},
        ],
        "risks": [{"point": "未提及管理经验", "evidence": "简历未提及"}],
    }, ensure_ascii=False)

    class _FakeClient:
        chat_model = RunnableLambda(lambda _messages: AIMessage(content=payload))

    monkeypatch.setattr(rp, "get_model_client", lambda: _FakeClient())

    out = json.loads(parse_resume(str(resume), [
        {"name": "Python 开发经验", "standard": "3 年以上"},
        {"name": "K8s", "standard": None},
    ]))

    assert out["basic"]["name"] == "张三"
    assert [s["name"] for s in out["suggestions"]] == ["Python 开发经验", "K8s"]
    assert out["suggestions"][1]["suggestion"] == "证据不足"
    # 只剩带真实证据的那一条优势
    assert [a["point"] for a in out["advantages"]] == ["5 年 Python 后端经验"]
    assert out["risks"] == [{"point": "未提及管理经验", "evidence": "简历未提及"}]


def test_real_llm_is_blocked_by_conftest_fixture(tmp_path):
    """conftest 的 LLM 隔离必须生效：未 mock 时禁止真实调用。"""
    resume = tmp_path / "resume.txt"
    resume.write_text("张三 5 年 Python 经验", encoding="utf-8")
    with pytest.raises(RuntimeError, match="禁止调用真实 LLM"):
        parse_resume(str(resume), [{"name": "Python 开发经验"}])
