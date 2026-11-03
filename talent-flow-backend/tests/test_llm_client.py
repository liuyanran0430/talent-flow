"""ModelClient 重试用例：可重试错误类型、尝试次数与退避参数配置。"""

from langchain_core.runnables.retry import RunnableRetry

from app.core.config import settings
from app.llm.client import RETRYABLE_ERRORS, ModelClient


def test_chat_model_retry_config(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    model = ModelClient(max_retries=2).chat_model

    assert isinstance(model, RunnableRetry)
    assert model.retry_exception_types == RETRYABLE_ERRORS
    # 总尝试次数 = 1 次首发 + 2 次重试
    assert model.max_attempt_number == 3
    assert model.wait_exponential_jitter is True
    assert model.exponential_jitter_params["initial"] == settings.LLM_RETRY_INITIAL_WAIT
    assert model.exponential_jitter_params["max"] == settings.LLM_RETRY_MAX_WAIT
