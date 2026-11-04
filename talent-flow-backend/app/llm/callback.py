"""模型调用埋点：每次 LLM 调用写入 llm_runs 表，并输出一条结构化日志。

以 LangChain callback 形式挂在 ChatOpenAI 实例上，业务侧无需改动调用方式。
结构化日志逐行 JSON 写入 logs/llm-YYYY-MM-DD.log，字段与排障问题一一对应：
- request_id            这次报错对应哪次请求（等于异步接口返回给前端的 request_id）
- user_id / session_id  影响的是谁、哪段对话
- model / prompt_version 当时用的是哪一版模型与提示词
- retrieval_ids         检索环节召回了什么（当前未接入 RAG，固定为空数组）
- tool_calls            外部系统是否正常（当前未接入工具调用，固定为空数组）
- latency_ms / tokens   慢在哪、贵在哪
- error_type            是模型错还是工具错
写库/写日志失败只记告警、绝不向上抛异常，避免影响主流程。
"""

import time

import openai
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from ..core.config import settings
from ..core.logging_config import (
    get_logger,
    get_prompt_version,
    get_request_id,
    get_retrieval_ids,
    get_session_id,
    get_user_id,
    write_llm_event,
)
from ..database import SessionLocal
from ..models.llm_run import LLMRun

logger = get_logger("llm")

# 异常类型 → 错误分类（顺序敏感：APITimeoutError 是 APIConnectionError 的子类）
ERROR_TYPE_MAP = (
    (openai.RateLimitError, "rate_limit"),
    (openai.APITimeoutError, "timeout"),
    (openai.APIConnectionError, "connection"),
    (openai.BadRequestError, "bad_request"),
    (openai.InternalServerError, "server_error"),
)


def _classify_error(error: BaseException) -> str:
    for exc_type, name in ERROR_TYPE_MAP:
        if isinstance(error, exc_type):
            return name
    return "unknown"


def _context_or_none(value: str) -> str | None:
    return None if value == "-" else value


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
    request_id: str | None,
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
                request_id=request_id,
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


def _record(
    *,
    model: str,
    latency_ms: int,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    status: str,
    error_type: str | None = None,
    error_message: str | None = None,
) -> None:
    """一次 LLM 调用的完整埋点：结构化日志 + llm_runs 明细。"""
    request_id = _context_or_none(get_request_id())
    event = {
        "request_id": request_id,
        "user_id": _context_or_none(get_user_id()),
        "session_id": _context_or_none(get_session_id()),
        "model": model or "-",
        "prompt_version": _context_or_none(get_prompt_version()),
        "retrieval_ids": get_retrieval_ids(),
        # 暂未接入工具调用，按空数组记录，便于后续扩展
        "tool_calls": [],
        "latency_ms": latency_ms,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "error_type": error_type,
        "status": status,
    }
    write_llm_event(event)
    _save_run(
        request_id=request_id,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        latency_ms=latency_ms,
        status=status,
        error_message=error_message,
    )


class LLMRunCallbackHandler(BaseCallbackHandler):
    """记录每次模型调用的开始时间，结束/异常时输出结构化日志并落库。"""

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
        _record(
            model=model,
            latency_ms=latency_ms,
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=total,
            status="success",
        )

    def on_llm_error(self, error: BaseException, *, run_id, **kwargs):  # noqa: ARG002
        key = str(run_id)
        started = self._started_at.pop(key, None)
        model = self._models.pop(key, settings.LLM_MODEL)
        latency_ms = int((time.perf_counter() - started) * 1000) if started else 0
        _record(
            model=model,
            latency_ms=latency_ms,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            status="error",
            error_type=_classify_error(error),
            error_message=str(error)[:2000],
        )
