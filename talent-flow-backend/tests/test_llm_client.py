"""ModelClient 错误处理策略用例（对照 LLM 错误码处理表）。"""

from langchain_core.runnables.retry import RunnableRetry

from app.core.config import settings
from app.llm.client import RETRYABLE_ERRORS, ModelClient


def test_chat_model_retry_config(monkeypatch):
    """429 限流/超时/连接中断/5xx → 指数退避 1s/2s/4s，共 3 次重试。"""
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    model = ModelClient(max_retries=3).chat_model

    assert isinstance(model, RunnableRetry)
    assert model.retry_exception_types == RETRYABLE_ERRORS
    # 总尝试次数 = 1 次首发 + 3 次重试（1s/2s/4s）
    assert model.max_attempt_number == 4
    assert model.wait_exponential_jitter is True
    assert model.exponential_jitter_params["initial"] == settings.LLM_RETRY_INITIAL_WAIT
    assert model.exponential_jitter_params["max"] == settings.LLM_RETRY_MAX_WAIT
    # jitter=0 → 退避严格为 1s/2s/4s，无随机成分
    assert model.exponential_jitter_params["jitter"] == settings.LLM_RETRY_JITTER == 0.0


def test_context_overflow_error_is_not_retryable():
    """上下文超限（400 BadRequest）不可重试：重发同样长度的 prompt 仍会被拒。"""
    import openai

    assert openai.BadRequestError not in RETRYABLE_ERRORS
    assert openai.RateLimitError in RETRYABLE_ERRORS
    assert openai.APITimeoutError in RETRYABLE_ERRORS


def test_chat_model_sets_hard_timeout_and_max_tokens(monkeypatch):
    """超时 → LLM_TIMEOUT 硬超时；上下文超限 → max_tokens 输出上限。"""
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    client = ModelClient()
    model = client.chat_model

    assert isinstance(model, RunnableRetry)
    # RunnableRetry.bound 即被包装的 ChatOpenAI 原始实例（timeout 字段实际名为 request_timeout）
    assert model.bound.request_timeout == settings.LLM_TIMEOUT
    assert model.bound.max_tokens == settings.LLM_MAX_TOKENS
    # SDK 内置重试关闭，统一由 with_retry 控制
    assert model.bound.max_retries == 0
