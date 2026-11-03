"""前端日志上报：接收浏览器端 warn/error 日志与未捕获异常，写入服务端日志文件"""
from fastapi import APIRouter, Request

from ..core.logging_config import get_audit_logger
from ..schemas.common import ApiResponse
from ..schemas.log import FrontendLog

router = APIRouter(prefix="/logs", tags=["logs"])

audit = get_audit_logger("frontend")


@router.post(
    "/frontend",
    response_model=ApiResponse[None],
    summary="接收前端日志（warn/error），写入服务端日志文件便于排障",
)
def receive_frontend_log(payload: FrontendLog, request: Request):
    client = request.client.host if request.client else "-"
    line = "[%s] session=%s page=%s client=%s url=%s [%s] %s" % (
        payload.level.upper(),
        payload.session_id or "-",
        payload.page or "-",
        client,
        payload.url or "-",
        payload.tag,
        payload.message,
    )
    if payload.user_agent:
        line += " | ua=" + payload.user_agent
    if payload.stack:
        line += "\n" + payload.stack
    # 前端上报时携带触发错误的那次操作的 trace_id，用它覆盖本次上报请求自己的 trace，
    # 保证「前端报错 → 后端对应请求日志」能用同一个 trace_id 串起来
    extra = {"trace_id": payload.trace_id} if payload.trace_id else {}
    if payload.level == "error":
        audit.error(line, extra=extra)
    else:
        audit.warning(line, extra=extra)
    return ApiResponse.ok(None)
