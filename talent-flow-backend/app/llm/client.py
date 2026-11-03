"""模型调用封装：ChatOpenAI 统一入口。

配置统一从 config.settings 读取（.env），各业务模块不再各自 load_dotenv / build_llm。
可重试错误（网络延迟/超时、连接中断、429 频次限制、5xx）会按指数退避在线程内 sleep 后重试。
"""

from functools import lru_cache

import openai
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI

from ..core.config import settings
from .callback import LLMRunCallbackHandler

# 可重试的模型调用异常：瞬时网络问题与服务端限流/故障
RETRYABLE_ERRORS = (
    openai.APIConnectionError,   # 网络延迟、连接中断
    openai.APITimeoutError,      # 请求超时
    openai.RateLimitError,       # 429 请求频次限制
    openai.InternalServerError,  # 5xx 服务端临时故障
)


class ModelClient:
    """ChatOpenAI 封装：懒构建 + 实例内缓存，参数集中管理。"""

    def __init__(
        self,
        *,
        model: str | None = None,
        temperature: float | None = None,
        timeout: int | None = None,
        max_retries: int | None = None,
    ) -> None:
        self._model = model or settings.LLM_MODEL
        self._temperature = settings.LLM_TEMPERATURE if temperature is None else temperature
        self._timeout = settings.LLM_TIMEOUT if timeout is None else timeout
        self._max_retries = settings.LLM_MAX_RETRIES if max_retries is None else max_retries
        self._chat_model: Runnable | None = None
        # 每次调用记录 model / token / latency / 状态到 llm_runs
        self._run_recorder = LLMRunCallbackHandler()

    @property
    def chat_model(self) -> Runnable:
        if self._chat_model is None:
            model = ChatOpenAI(
                model=self._model,
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_API_BASE,
                temperature=self._temperature,
                timeout=self._timeout,
                # 关闭 SDK 内置重试，统一由下方 with_retry 控制，便于按配置睡眠并记录每次尝试
                max_retries=0,
                callbacks=[self._run_recorder],
            )
            # 可重试错误：指数退避（1s 起、单次最多 10s、带抖动），同步调用时在线程内 sleep 后重发
            self._chat_model = model.with_retry(
                retry_if_exception_type=RETRYABLE_ERRORS,
                wait_exponential_jitter=True,
                exponential_jitter_params={
                    "initial": settings.LLM_RETRY_INITIAL_WAIT,
                    "max": settings.LLM_RETRY_MAX_WAIT,
                    "jitter": 1.0,
                },
                stop_after_attempt=self._max_retries + 1,
            )
        return self._chat_model


@lru_cache
def get_model_client() -> ModelClient:
    """进程级单例：所有业务共享同一套 LLM 配置。"""
    return ModelClient()
