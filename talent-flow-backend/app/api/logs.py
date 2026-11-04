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
    # 前端上报时携带触发错误的那次 LLM 请求的 request_id，覆盖本次上报请求自己的上下文，
    # 保证「前端报错 → 后端对应 LLM 请求日志」能用同一 request_id 串起来
    extra = {}
    if payload.request_id:
        extra["request_id"] = payload.request_id
    if payload.level == "error":
        audit.error(line, extra=extra)
    else:
        audit.warning(line, extra=extra)
    return ApiResponse.ok(None)
