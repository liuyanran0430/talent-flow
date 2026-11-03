"""llm_runs 埋点用例：验证模型调用成功/失败都会落库。"""

import uuid

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from app.database import SessionLocal
from app.llm.callback import LLMRunCallbackHandler
from app.models import LLMRun


def _response(prompt_tokens: int, completion_tokens: int) -> LLMResult:
    message = AIMessage(
        content="ok",
        usage_metadata={
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    )
    return LLMResult(
        generations=[[ChatGeneration(message=message)]],
        llm_output={
            "token_usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            }
        },
    )


def test_success_run_recorded():
    handler = LLMRunCallbackHandler()
    run_id = uuid.uuid4()
    handler.on_chat_model_start({"kwargs": {"model_name": "qwen-max"}}, [], run_id=run_id)
    handler.on_llm_end(_response(12, 30), run_id=run_id)

    with SessionLocal() as db:
        row = db.query(LLMRun).one()
    assert row.model == "qwen-max"
    assert row.prompt_tokens == 12
    assert row.completion_tokens == 30
    assert row.total_tokens == 42
    assert row.status == "success"
    assert row.latency_ms >= 0


def test_error_run_recorded():
    handler = LLMRunCallbackHandler()
    run_id = uuid.uuid4()
    handler.on_chat_model_start({}, [], run_id=run_id)
    handler.on_llm_error(RuntimeError("boom"), run_id=run_id)

    with SessionLocal() as db:
        row = db.query(LLMRun).one()
    assert row.status == "error"
    assert row.total_tokens == 0
    assert "boom" in (row.error_message or "")
