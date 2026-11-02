"""前端日志上报：接收浏览器端 warn/error 日志与未捕获异常，写入服务端日志文件"""
from fastapi import APIRouter, Request

from ..logging_config import get_audit_logger
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
    if payload.level == "error":
        audit.error(line)
    else:
        audit.warning(line)
    return ApiResponse.ok(None)
