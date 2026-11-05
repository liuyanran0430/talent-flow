"""模型调用封装：ChatOpenAI 统一入口。

配置统一从 config.settings 读取（.env），各业务模块不再各自 load_dotenv / build_llm。

错误处理策略（对照 LLM 错误码处理表）：
- 429 限流（供应商拒绝请求）→ 指数退避重试 1s/2s/4s（LLM_MAX_RETRIES=3，LLM_RETRY_JITTER=0）
- 超时（响应迟迟不返回）→ LLM_TIMEOUT 硬超时 + 上面的重试上限
- 上下文超限（Prompt 过长被拒）→ 不重试；由各业务预处理截断输入（简历/JD/检索片段）+ LLM_MAX_TOKENS 输出上限
- JSON 解析失败（模型输出不合规）→ 不在此层处理，见 llm/parse_retry.py：重试一次后降级转人工
"""

from functools import lru_cache

import openai
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI

from ..core.config import settings
from .callback import LLMRunCallbackHandler

# 可重试的模型调用异常：瞬时网络问题与服务端限流/故障。
# 上下文超限（400 BadRequest）不在其中：重发同样长度的 prompt 仍会被拒，应由输入截断解决。
RETRYABLE_ERRORS = (
    openai.APIConnectionError,   # 网络延迟、连接中断
    openai.APITimeoutError,      # 请求超时（LLM_TIMEOUT 硬超时触发）
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
        max_tokens: int | None = None,
    ) -> None:
        self._model = model or settings.LLM_MODEL
        self._temperature = settings.LLM_TEMPERATURE if temperature is None else temperature
        self._timeout = settings.LLM_TIMEOUT if timeout is None else timeout
        self._max_retries = settings.LLM_MAX_RETRIES if max_retries is None else max_retries
        self._max_tokens = settings.LLM_MAX_TOKENS if max_tokens is None else max_tokens
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
                # 硬超时：请求超过该秒数视为失败（配合重试上限）
                timeout=self._timeout,
                # 输出 token 上限：配合各业务的输入截断，控制总上下文占用
                max_tokens=self._max_tokens,
                # 关闭 SDK 内置重试，统一由下方 with_retry 控制，便于按配置睡眠并记录每次尝试
                max_retries=0,
                callbacks=[self._run_recorder],
            )
            # 可重试错误（429 限流/超时/连接中断/5xx）：指数退避 1s/2s/4s，
            # 同步调用时由 tenacity 在当前线程内 sleep 后重发；jitter=0 保证严格按 1s/2s/4s
            self._chat_model = model.with_retry(
                retry_if_exception_type=RETRYABLE_ERRORS,
                wait_exponential_jitter=True,
                exponential_jitter_params={
                    "initial": settings.LLM_RETRY_INITIAL_WAIT,
                    "max": settings.LLM_RETRY_MAX_WAIT,
                    "jitter": settings.LLM_RETRY_JITTER,
                },
                stop_after_attempt=self._max_retries + 1,
            )
        return self._chat_model


@lru_cache
def get_model_client() -> ModelClient:
    """进程级单例：所有业务共享同一套 LLM 配置。"""
    return ModelClient()
