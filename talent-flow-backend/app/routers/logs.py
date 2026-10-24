"""前端日志上报：接收浏览器端 warn/error 日志与未捕获异常，写入服务端日志文件"""
from fastapi import APIRouter

from ..logging_config import get_logger
from ..schemas.common import ApiResponse
from ..schemas.log import FrontendLog

router = APIRouter(prefix="/logs", tags=["logs"])

logger = get_logger("frontend")


@router.post(
    "/frontend",
    response_model=ApiResponse[None],
    summary="接收前端日志（warn/error），写入服务端日志文件便于排障",
)
def receive_frontend_log(payload: FrontendLog):
    line = "[%s] [%s] %s" % (payload.level.upper(), payload.tag, payload.message)
    if payload.stack:
        line += "\n" + payload.stack
    if payload.level == "error":
        logger.error(line)
    else:
        logger.warning(line)
    return ApiResponse.ok(None)
