"""统一日志配置：请求级 trace id、业务流水与错误日志同时输出到控制台与 logs/ 目录。

文件说明：
- logs/app.log       全量日志（INFO 及以上），10MB 轮转，保留 5 份
- logs/errors.log    仅 ERROR 及以上，5MB 轮转，保留 5 份
- logs/business.log  业务关键事件流水（谁在何时对哪个对象做了什么），10MB 轮转，保留 5 份

全流程追溯方式：
- 每个 HTTP 请求分配 request id（优先复用前端传入的 X-Request-ID），日志行包含
  `rid=xxxxxxxx`，响应头同时回传 X-Request-ID；
- 前端 warn/error 日志携带 session_id，后端接收时一并落盘；
- 后台任务（简历解析、要求重算）使用独立 task_id，并沿用触发请求的 request id。
"""
import logging
import os
import uuid
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler

# 后端项目根目录（talent-flow-backend/）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, "logs")

# 请求级 trace id：在 FastAPI 中间件中写入，日志 Filter 自动注入到每条日志
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

LOG_FORMAT = "%(asctime)s | %(levelname)-7s | rid=%(request_id)s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def new_request_id() -> str:
    """生成短 trace id（12 位十六进制），便于人工检索"""
    return uuid.uuid4().hex[:12]


def set_request_id(request_id: str):
    """绑定当前上下文的 trace id，返回用于恢复的 token"""
    return request_id_var.set(request_id or "-")


def reset_request_id(token) -> None:
    """恢复上一个 trace id（请求结束后调用，避免上下文串号）"""
    try:
        request_id_var.reset(token)
    except ValueError:
        pass


def get_request_id() -> str:
    return request_id_var.get()


class RequestIdFilter(logging.Filter):
    """把当前上下文的 trace id 注入日志记录（不覆盖显式传入的值）"""

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "request_id", None):
            record.request_id = request_id_var.get()
        return True


_request_id_filter = RequestIdFilter()


def _make_formatter() -> logging.Formatter:
    return logging.Formatter(LOG_FORMAT, DATE_FORMAT)


def _make_file_handler(filename: str, level: int, max_bytes: int, backup_count: int) -> RotatingFileHandler:
    handler = RotatingFileHandler(
        os.path.join(LOG_DIR, filename),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(_make_formatter())
    handler.addFilter(_request_id_filter)
    # 标记本工程挂载的 handler，防止 uvicorn 热重载（模块重新导入）时重复添加
    handler._talent_flow = True
    return handler


def _ensure_handlers(logger: logging.Logger, handlers: list[logging.Handler]) -> None:
    """仅在 logger 尚未挂载本工程 handler 时添加（幂等，兼容 --reload 多次执行）"""
    if any(getattr(h, "_talent_flow", False) for h in logger.handlers):
        return
    for h in handlers:
        logger.addHandler(h)


def setup_logging() -> None:
    """初始化日志：业务日志、业务流水、uvicorn 既有日志均落盘"""
    os.makedirs(LOG_DIR, exist_ok=True)

    all_file = _make_file_handler("app.log", logging.INFO, 10 * 1024 * 1024, 5)
    err_file = _make_file_handler("errors.log", logging.ERROR, 5 * 1024 * 1024, 5)
    business_file = _make_file_handler("business.log", logging.INFO, 10 * 1024 * 1024, 5)

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(_make_formatter())
    console.addFilter(_request_id_filter)
    console._talent_flow = True

    # app.* 业务日志：控制台 + 全量文件 + 错误文件
    app_root = logging.getLogger("app")
    app_root.setLevel(logging.INFO)
    app_root.propagate = False
    _ensure_handlers(app_root, [console, all_file, err_file])

    # app.audit.* 业务流水：额外写 business.log，并向 app 根 logger 传播（控制台 + app.log）
    audit_root = logging.getLogger("app.audit")
    audit_root.setLevel(logging.INFO)
    audit_root.propagate = True
    _ensure_handlers(audit_root, [business_file])

    # uvicorn.error：run_parse / generate / recalculate 等既有失败堆栈走此 logger，补挂文件输出
    # （uvicorn 已为其配置控制台输出，只加文件，不重复控制台）
    uvicorn_error = logging.getLogger("uvicorn.error")
    _ensure_handlers(uvicorn_error, [all_file, err_file])


def get_logger(name: str = "app") -> logging.Logger:
    """获取业务子 logger（app.xxx），自动向 app 根 logger 传播输出"""
    return logging.getLogger(name if name.startswith("app") else f"app.{name}")


def get_audit_logger(name: str = "audit") -> logging.Logger:
    """获取业务流水 logger（app.audit.xxx），额外写入 logs/business.log"""
    if name.startswith("app.audit"):
        return logging.getLogger(name)
    return logging.getLogger(f"app.audit.{name}")
