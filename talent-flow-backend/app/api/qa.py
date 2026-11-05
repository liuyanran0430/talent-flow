"""招聘知识问答接口：异步任务 + 前端轮询 GET /tasks/{request_id}。"""

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from ..core.logging_config import (
    get_audit_logger,
    get_logger,
    reset_session_id,
    set_request_id,
    set_session_id,
)
from ..database import SessionLocal, get_db
from ..schemas.common import ApiResponse
from ..schemas.qa import QaAskRequest
from ..services.async_tasks import create_task, execute_task
from ..services.qa_service import answer_question

router = APIRouter(prefix="/qa", tags=["qa"])

logger = get_logger("qa")
audit = get_audit_logger("qa")


@router.post(
    "/ask",
    response_model=ApiResponse[dict],
    summary="招聘知识问答提问（异步任务，凭 request_id 轮询结果）",
)
def ask(payload: QaAskRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    request_id = create_task(db, "qa_answer")
    # 触发接口属于 LLM 相关接口，本次请求日志绑定 request_id
    set_request_id(request_id)
    logger.info(
        "知识问答任务已入队 request_id=%s session_id=%s question=%s",
        request_id, payload.session_id, payload.question[:60],
    )
    audit.info(
        "知识问答触发 request_id=%s session_id=%s pending=%s",
        request_id, payload.session_id, bool(payload.pending_intent),
    )
    background_tasks.add_task(
        execute_task,
        request_id,
        lambda: _run_qa_task(payload, request_id),
    )
    return ApiResponse.ok({"request_id": request_id})


def _run_qa_task(payload: QaAskRequest, request_id: str) -> dict:
    """后台任务：执行分类、检索、生成与校验，返回任务结果结构。"""
    db = SessionLocal()
    session_token = set_session_id(payload.session_id)
    try:
        result = answer_question(
            db,
            payload.question,
            session_id=payload.session_id,
            history=payload.history,
            pending_intent=payload.pending_intent,
        )
        result["session_id"] = payload.session_id
        result["request_id"] = request_id
        audit.info(
            "知识问答完成 request_id=%s category=%s hit=%s answerable=%s latency_ms=%s",
            request_id,
            result.get("category"),
            result.get("hit"),
            (result.get("answer") or {}).get("answerable"),
            result.get("latency_ms"),
        )
        return result
    finally:
        reset_session_id(session_token)
        db.close()
