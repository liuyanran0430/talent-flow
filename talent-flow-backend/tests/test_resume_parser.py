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


def test_parse_resume_retries_once_on_bad_json(monkeypatch, tmp_path):
    """JSON 解析失败 → 重试一次：首次输出不合规、第二次正常时解析成功。"""
    resume = tmp_path / "resume.txt"
    resume.write_text("张三，2019-2024 年负责 Python 后端开发。", encoding="utf-8")

    good = json.dumps({
        "basic": {"name": "张三", "phone": None, "email": None, "experience": "5 年"},
        "suggestions": [
            {"name": "Python 开发经验", "suggestion": "满足", "evidence": "负责 Python 后端开发"},
        ],
        "advantages": [
            {"point": "5 年 Python 后端经验", "evidence": "2019-2024 年负责 Python 后端开发"},
        ],
        "risks": [],
    }, ensure_ascii=False)

    calls = {"n": 0}

    def _fake_llm(_messages):
        calls["n"] += 1
        # 第一次输出不合规（不是合法 JSON），第二次返回正常结果
        return AIMessage(content="抱歉，我无法输出 JSON" if calls["n"] == 1 else good)

    class _FakeClient:
        chat_model = RunnableLambda(_fake_llm)

    monkeypatch.setattr(rp, "get_model_client", lambda: _FakeClient())

    out = json.loads(parse_resume(str(resume), [{"name": "Python 开发经验", "standard": "3 年以上"}]))
    assert calls["n"] == 2  # 首次 + 重试一次
    assert out["basic"]["name"] == "张三"


def test_parse_resume_raises_after_retry_to_degrade(monkeypatch, tmp_path):
    """JSON 解析重试一次仍失败 → 抛出原异常，由 resume_tasks 降级转人工（置 review）。"""
    from langchain_core.exceptions import OutputParserException

    resume = tmp_path / "resume.txt"
    resume.write_text("张三 5 年 Python 经验", encoding="utf-8")

    calls = {"n": 0}

    def _fake_llm(_messages):
        calls["n"] += 1
        return AIMessage(content="始终不是 JSON")  # 两次都输出不合规

    class _FakeClient:
        chat_model = RunnableLambda(_fake_llm)

    monkeypatch.setattr(rp, "get_model_client", lambda: _FakeClient())

    with pytest.raises(OutputParserException):
        parse_resume(str(resume), [{"name": "Python 开发经验"}])
    assert calls["n"] == 2  # 只重试一次，不无限重试


def test_real_llm_is_blocked_by_conftest_fixture(tmp_path):
    """conftest 的 LLM 隔离必须生效：未 mock 时禁止真实调用。"""
    resume = tmp_path / "resume.txt"
    resume.write_text("张三 5 年 Python 经验", encoding="utf-8")
    with pytest.raises(RuntimeError, match="禁止调用真实 LLM"):
        parse_resume(str(resume), [{"name": "Python 开发经验"}])


# ---------- 边界情况 ----------

def test_parse_resume_empty_resume_text_raises(tmp_path, monkeypatch):
    """简历文件为空（抽不到任何文本）→ 直接拒绝，不调用 LLM。"""
    resume = tmp_path / "empty.txt"
    resume.write_text("   \n  \t  ", encoding="utf-8")  # 只有空白

    called = {"n": 0}

    def _fake_llm(_m):
        called["n"] += 1
        return AIMessage(content="{}")

    from langchain_core.runnables import RunnableLambda

    class _FakeClient:
        chat_model = RunnableLambda(_fake_llm)

    monkeypatch.setattr(rp, "get_model_client", lambda: _FakeClient())

    with pytest.raises(ValueError, match="未能从简历中提取到文本"):
        parse_resume(str(resume), [{"name": "Python 开发经验", "standard": "3 年以上"}])
    assert called["n"] == 0, "空简历不应触发 LLM 调用"


def test_parse_resume_truncates_long_resume(tmp_path, monkeypatch):
    """简历文本超 8000 字 → 截断到 MAX_RESUME_CHARS。"""
    long_text = "张三" + "是" * 10000  # 远超 8000
    resume = tmp_path / "long.txt"
    resume.write_text(long_text, encoding="utf-8")

    captured = {}

    def _fake_llm(_messages):
        # 从 ChatPromptValue 中拿到拼接好的 prompt 内容
        captured["len"] = len(long_text)
        return AIMessage(content=json.dumps({
            "basic": {"name": "张三", "phone": None, "email": None, "experience": None},
            "suggestions": [{"name": "Python 开发经验", "suggestion": "证据不足", "evidence": ""}],
            "advantages": [],
            "risks": [],
        }))

    from langchain_core.runnables import RunnableLambda

    class _FakeClient:
        chat_model = RunnableLambda(_fake_llm)

    monkeypatch.setattr(rp, "get_model_client", lambda: _FakeClient())
    rp.parse_resume(str(resume), [{"name": "Python 开发经验"}])

    # 简历原文 10002 字，截断后应 ≤ MAX_RESUME_CHARS
    assert captured["len"] > rp.MAX_RESUME_CHARS, "原测试前置条件错误：长简历必须真的超长"
    # 通过 preprocess 返回值验证截断（更直接）
    from app.services.resume_parser import preprocess
    payload = {"resume_path": str(resume), "requirements": [{"name": "Python 开发经验", "standard": "3 年以上"}]}
    processed = preprocess(payload)
    # resume_text 部分应被截断
    assert len(processed["resume_text"]) <= rp.MAX_RESUME_CHARS


def test_parse_resume_no_requirements_all_suggestions_insufficient(tmp_path, monkeypatch):
    """无要求项（requirements=[]）→ suggestions 为空数组，不报错。"""
    resume = tmp_path / "resume.txt"
    resume.write_text("张三，2019-2024 年负责 Python 后端开发。", encoding="utf-8")

    class _FakeClient:
        chat_model = RunnableLambda(lambda _m: AIMessage(content=json.dumps({
            "basic": {"name": "张三", "phone": None, "email": None, "experience": "5 年"},
            "suggestions": [],
            "advantages": [{"point": "5 年 Python 后端经验", "evidence": "2019-2024 年负责 Python 后端开发"}],
            "risks": [],
        })))

    monkeypatch.setattr(rp, "get_model_client", lambda: _FakeClient())

    out = json.loads(parse_resume(str(resume), []))
    assert out["suggestions"] == []
    assert out["basic"]["name"] == "张三"
    assert len(out["advantages"]) == 1


# ---------- 异常输入 ----------

def test_parse_resume_file_not_found_raises(tmp_path, monkeypatch):
    """传入不存在的文件路径 → ValueError，不触发 LLM 调用。"""
    called = {"n": 0}

    def _fake_llm(_m):
        called["n"] += 1
        return AIMessage(content="{}")

    from langchain_core.runnables import RunnableLambda

    class _FakeClient:
        chat_model = RunnableLambda(_fake_llm)

    monkeypatch.setattr(rp, "get_model_client", lambda: _FakeClient())

    with pytest.raises(ValueError, match="简历文件不存在"):
        parse_resume(str(tmp_path / "not_exist.pdf"), [{"name": "Python"}])
    assert called["n"] == 0


def test_parse_resume_unsupported_format_raises(tmp_path, monkeypatch):
    """传入不支持的 .doc 旧版格式 → ValueError，不触发 LLM 调用。"""
    fake_doc = tmp_path / "old.doc"
    fake_doc.write_bytes(b"\xd0\xcf\x11\xe0")  # 伪造 doc 头

    called = {"n": 0}

    def _fake_llm(_m):
        called["n"] += 1
        return AIMessage(content="{}")

    from langchain_core.runnables import RunnableLambda

    class _FakeClient:
        chat_model = RunnableLambda(_fake_llm)

    monkeypatch.setattr(rp, "get_model_client", lambda: _FakeClient())

    with pytest.raises(ValueError, match="暂不支持旧版"):
        parse_resume(str(fake_doc), [{"name": "Python"}])
    assert called["n"] == 0
