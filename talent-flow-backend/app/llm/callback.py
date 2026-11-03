"""模型调用埋点：把每次 LLM 调用的 model / token / latency / 状态写入 llm_runs 表。

以 LangChain callback 形式挂在 ChatOpenAI 实例上，业务侧无需改动调用方式。
写库失败只记日志、绝不向上抛异常，避免影响主流程。
"""

import time

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from ..core.config import settings
from ..core.logging_config import get_logger, get_trace_id
from ..database import SessionLocal
from ..models.llm_run import LLMRun

logger = get_logger("llm")


def _extract_usage(response: LLMResult) -> tuple[int, int, int]:
    """从 LLMResult 中解析 token 用量，兼容 OpenAI 与新版 usage_metadata。"""
    llm_output = response.llm_output or {}
    usage = llm_output.get("token_usage") or llm_output.get("usage") or {}
    prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    total = int(usage.get("total_tokens") or (prompt + completion))

    if not total:
        # 部分模型只在 message.usage_metadata 上带用量
        for generation_list in response.generations:
            for generation in generation_list:
                meta = getattr(getattr(generation, "message", None), "usage_metadata", None) or {}
                prompt = prompt or int(meta.get("input_tokens") or 0)
                completion = completion or int(meta.get("output_tokens") or 0)
                total = total or int(meta.get("total_tokens") or (prompt + completion))
                if total:
                    return prompt, completion, total
    return prompt, completion, total


def _extract_model(serialized: dict | None) -> str:
    kwargs = (serialized or {}).get("kwargs") or {}
    return kwargs.get("model_name") or kwargs.get("model") or settings.LLM_MODEL


def _save_run(
    *,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    latency_ms: int,
    status: str,
    error_message: str | None = None,
) -> None:
    """独立会话写入 llm_runs；任何异常只记录告警，不影响模型调用本身。"""
    db = SessionLocal()
    try:
        db.add(
            LLMRun(
                trace_id=get_trace_id() if get_trace_id() != "-" else None,
                model=model or "-",
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                latency_ms=latency_ms,
                status=status,
                error_message=error_message,
            )
        )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning("llm_runs 写入失败 model=%s status=%s error=%s", model, status, e)
    finally:
        db.close()


class LLMRunCallbackHandler(BaseCallbackHandler):
    """记录每次模型调用的开始时间，结束/异常时落库。"""

    def __init__(self) -> None:
        self._started_at: dict[str, float] = {}
        self._models: dict[str, str] = {}

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):  # noqa: ARG002
        key = str(run_id)
        self._started_at[key] = time.perf_counter()
        self._models[key] = _extract_model(serialized)

    def on_llm_end(self, response: LLMResult, *, run_id, **kwargs):  # noqa: ARG002
        key = str(run_id)
        started = self._started_at.pop(key, None)
        model = self._models.pop(key, settings.LLM_MODEL)
        latency_ms = int((time.perf_counter() - started) * 1000) if started else 0
        prompt, completion, total = _extract_usage(response)
        _save_run(
            model=model,
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=total,
            latency_ms=latency_ms,
            status="success",
        )

    def on_llm_error(self, error: BaseException, *, run_id, **kwargs):  # noqa: ARG002
        key = str(run_id)
        started = self._started_at.pop(key, None)
        model = self._models.pop(key, settings.LLM_MODEL)
        latency_ms = int((time.perf_counter() - started) * 1000) if started else 0
        _save_run(
            model=model,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            latency_ms=latency_ms,
            status="error",
            error_message=str(error)[:2000],
        )
