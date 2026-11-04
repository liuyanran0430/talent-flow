"""统一日志配置：request id 贯穿 LLM 请求与后台任务，日志同时输出到控制台与按天文件。

文件说明：
- logs/app-YYYY-MM-DD.log       后端全量日志（业务、访问、错误堆栈），每天一个文件，跨天自动切换
- logs/frontend-YYYY-MM-DD.log  前端上报日志（浏览器 warn/error、未捕获异常），与后端日志分文件保存
- logs/llm-YYYY-MM-DD.log       LLM 调用结构化日志（每行一个 JSON），用于排障与用量分析

全流程追溯方式：
- request_id 由 LLM 异步接口生成并返回给前端（同时落库 async_tasks），后台任务与模型调用共用该 id；
- 只有调用 LLM 的接口会带 request_id，其余请求日志该字段为 `-`；
- 前端 warn/error 日志携带 session_id 与 request_id，后端接收时一并落盘。

日志格式（app / frontend）：
    时间 | 级别 | request_id=xxx | logger | 消息

LLM 结构化日志格式（llm，逐行 JSON）：
    {"request_id": "...", "user_id": null, "session_id": "...", "model": "...",
     "prompt_version": "...", "retrieval_ids": [], "tool_calls": [],
     "latency_ms": 123, "prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30,
     "error_type": null, "status": "success"}
"""
import json
import logging
import os
from contextvars import ContextVar
from datetime import date

# 后端项目根目录（talent-flow-backend/）：本文件位于 app/core/，需上溯三层
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG_DIR = os.path.join(BASE_DIR, "logs")

# LLM 请求 id：异步任务入口绑定，等于接口返回给前端的 request_id；未绑定时为 "-"
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
# 会话 id：前端通过 X-Session-ID 请求头传入
session_id_var: ContextVar[str] = ContextVar("session_id", default="-")
# 用户 id：当前系统无登录体系，默认 "-"（预留）
user_id_var: ContextVar[str] = ContextVar("user_id", default="-")
# Prompt 版本：由解析器在调用 LLM 前绑定，便于定位「当时用的是哪一版提示词」
prompt_version_var: ContextVar[str] = ContextVar("prompt_version", default="-")

LOG_FORMAT = "%(asctime)s | %(levelname)-7s | request_id=%(request_id)s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _set(var: ContextVar, value: str | None):
    return var.set(value or "-")


def _reset(var: ContextVar, token) -> None:
    try:
        var.reset(token)
    except ValueError:
        pass


def set_request_id(request_id: str):
    """绑定当前上下文的 request_id，返回用于恢复的 token"""
    return _set(request_id_var, request_id)


def reset_request_id(token) -> None:
    _reset(request_id_var, token)


def get_request_id() -> str:
    return request_id_var.get()


def set_session_id(session_id: str | None):
    return _set(session_id_var, session_id)


def reset_session_id(token) -> None:
    _reset(session_id_var, token)


def get_session_id() -> str:
    return session_id_var.get()


def set_user_id(user_id: str | None):
    return _set(user_id_var, user_id)


def reset_user_id(token) -> None:
    _reset(user_id_var, token)


def get_user_id() -> str:
    return user_id_var.get()


def set_prompt_version(prompt_version: str):
    return _set(prompt_version_var, prompt_version)


def reset_prompt_version(token) -> None:
    _reset(prompt_version_var, token)


def get_prompt_version() -> str:
    return prompt_version_var.get()


class ContextFilter(logging.Filter):
    """把当前上下文的 request_id 注入日志记录（不覆盖显式传入的值）"""

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "request_id", None):
            record.request_id = request_id_var.get()
        return True


_context_filter = ContextFilter()


def _make_formatter() -> logging.Formatter:
    return logging.Formatter(LOG_FORMAT, DATE_FORMAT)


class DailyFileHandler(logging.FileHandler):
    """按天切换的日志文件：写入 logs/<prefix>-YYYY-MM-DD.log，跨天自动换新文件。"""

    def __init__(self, log_dir: str, level: int, prefix: str = "app") -> None:
        self._log_dir = log_dir
        self._prefix = prefix
        self._day = date.today().isoformat()
        super().__init__(
            os.path.join(log_dir, f"{prefix}-{self._day}.log"), mode="a", encoding="utf-8"
        )
        self.setLevel(level)
        self.setFormatter(_make_formatter())
        self.addFilter(_context_filter)
        # 标记本工程挂载的 handler，防止 uvicorn 热重载（模块重新导入）时重复添加
        self._talent_flow = True

    def emit(self, record: logging.LogRecord) -> None:
        day = date.today().isoformat()
        if day != self._day:
            self._day = day
            self.baseFilename = os.path.abspath(
                os.path.join(self._log_dir, f"{self._prefix}-{day}.log")
            )
            if self.stream:
                self.stream.close()
                self.stream = None
            self.stream = self._open()
        super().emit(record)


def _ensure_handlers(logger: logging.Logger, handlers: list[logging.Handler]) -> None:
    """仅在 logger 尚未挂载本工程 handler 时添加（幂等，兼容 --reload 多次执行）"""
    if any(getattr(h, "_talent_flow", False) for h in logger.handlers):
        return
    for h in handlers:
        logger.addHandler(h)


def setup_logging() -> None:
    """初始化日志：后端日志、前端上报日志、LLM 结构化日志分文件按天写入"""
    os.makedirs(LOG_DIR, exist_ok=True)

    daily_file = DailyFileHandler(LOG_DIR, logging.INFO, prefix="app")
    frontend_file = DailyFileHandler(LOG_DIR, logging.INFO, prefix="frontend")

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(_make_formatter())
    console.addFilter(_context_filter)
    console._talent_flow = True

    # app.* 业务日志（含 app.audit.* 业务流水）：控制台 + 当天文件
    app_root = logging.getLogger("app")
    app_root.setLevel(logging.INFO)
    app_root.propagate = False
    _ensure_handlers(app_root, [console, daily_file])

    # app.audit.* 业务流水：只向 app 根 logger 传播
    audit_root = logging.getLogger("app.audit")
    audit_root.setLevel(logging.INFO)
    audit_root.propagate = True

    # 前端上报日志：独立文件，不再混入后端 app 日志
    frontend_root = logging.getLogger("app.audit.frontend")
    frontend_root.setLevel(logging.INFO)
    frontend_root.propagate = False
    _ensure_handlers(frontend_root, [console, frontend_file])

    # LLM 结构化日志：llm-YYYY-MM-DD.log，逐行 JSON，只落文件（不打控制台）
    llm_file = DailyFileHandler(LOG_DIR, logging.INFO, prefix="llm")
    llm_file.setFormatter(logging.Formatter("%(message)s"))
    llm_logger = logging.getLogger("app.llm.structured")
    llm_logger.setLevel(logging.INFO)
    llm_logger.propagate = False
    _ensure_handlers(llm_logger, [llm_file])


def write_llm_event(event: dict) -> None:
    """写入一条 LLM 结构化日志（JSON 单行）；失败不影响主流程。"""
    try:
        logging.getLogger("app.llm.structured").info(
            json.dumps(event, ensure_ascii=False, default=str)
        )
    except Exception:  # 日志异常绝不阻断业务
        pass


def get_logger(name: str = "app") -> logging.Logger:
    """获取业务子 logger（app.xxx），自动向 app 根 logger 传播输出"""
    return logging.getLogger(name if name.startswith("app") else f"app.{name}")


def get_audit_logger(name: str = "audit") -> logging.Logger:
    """获取业务流水 logger（app.audit.xxx），随 app 根 logger 写入当天文件"""
    if name.startswith("app.audit"):
        return logging.getLogger(name)
    return logging.getLogger(f"app.audit.{name}")
