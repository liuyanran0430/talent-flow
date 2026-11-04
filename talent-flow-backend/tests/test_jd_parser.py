"""JD 解析错误处理用例：输入截断（上下文超限防御）+ JSON 解析失败重试一次（LLM 全部 mock）。"""

import json

import pytest
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from app.services import jd_parser as jp
from app.services.jd_parser import MAX_JD_CHARS, parse_jd, preprocess


_GOOD = json.dumps({
    "items": [
        {"name": "Python", "type": "必须", "importance": "高", "standard": "3 年以上开发经验"},
    ]
}, ensure_ascii=False)


def test_preprocess_truncates_long_jd():
    """上下文超限防御：超长 JD 清洗后按 MAX_JD_CHARS 截断。"""
    jd = "精通 Python。 " * 2000  # 清洗后远超上限
    out = preprocess(jd)
    assert len(out["jd"]) == MAX_JD_CHARS


def test_parse_jd_retries_once_on_bad_json(monkeypatch):
    """JSON 解析失败 → 重试一次：首次不合规、第二次正常时生成成功。"""
    calls = {"n": 0}

    def _fake_llm(_messages):
        calls["n"] += 1
        return AIMessage(content="无法输出 JSON" if calls["n"] == 1 else _GOOD)

    class _FakeClient:
        chat_model = RunnableLambda(_fake_llm)

    monkeypatch.setattr(jp, "get_model_client", lambda: _FakeClient())

    out = json.loads(parse_jd("岗位：Python 后端，要求 3 年经验。"))
    assert calls["n"] == 2
    assert out["items"][0]["name"] == "Python"


def test_parse_jd_raises_after_retry_to_degrade(monkeypatch):
    """JSON 重试一次仍失败 → 抛出原异常，由接口降级转人工（HR 手动填写要求项）。"""
    calls = {"n": 0}

    def _fake_llm(_messages):
        calls["n"] += 1
        return AIMessage(content="还是不是 JSON")

    class _FakeClient:
        chat_model = RunnableLambda(_fake_llm)

    monkeypatch.setattr(jp, "get_model_client", lambda: _FakeClient())

    with pytest.raises(OutputParserException):
        parse_jd("岗位：Python 后端。")
    assert calls["n"] == 2  # 只重试一次


def test_parse_jd_empty_text_rejected():
    """空 JD 直接拒绝，不触发 LLM。"""
    with pytest.raises(ValueError, match="JD 文本不能为空"):
        parse_jd("   ")
