"""统一日志配置：trace id / task id 贯穿请求与后台任务，日志同时输出到控制台与按天文件。

文件说明：
- logs/app-YYYY-MM-DD.log  全量日志（INFO 及以上），每天一个文件，跨天自动切换
- 不再单独写 errors.log / business.log / uvicorn.err.log；错误堆栈、业务流水、访问日志统一进当天文件

全流程追溯方式：
- 前端一次用户操作生成一个 trace_id（X-Trace-ID 请求头），后端优先复用、缺失时自动生成，
  日志行包含 `trace_id=xxxxxxxxxxxxxxxx`，响应头回传 X-Trace-ID；
- 后台任务（简历解析、要求重算）沿用触发请求的 trace_id，并另行绑定 task_id 字段，便于区分同一操作内的多个异步任务；
- 前端 warn/error 日志携带 session_id 与 trace_id，后端接收时一并落盘。

日志格式：
    时间 | 级别 | trace_id=xxx | task=xxx | logger | 消息
"""
import logging
import os
import uuid
from contextvars import ContextVar
from datetime import date

# 后端项目根目录（talent-flow-backend/）：本文件位于 app/core/，需上溯三层
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG_DIR = os.path.join(BASE_DIR, "logs")

# 请求级 trace id：在 FastAPI 中间件中写入，日志 Filter 自动注入到每条日志
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="-")
# 后台任务 id：在后台任务入口绑定，未绑定时为 "-"
task_id_var: ContextVar[str] = ContextVar("task_id", default="-")

LOG_FORMAT = "%(asctime)s | %(levelname)-7s | trace_id=%(trace_id)s | task=%(task_id)s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def new_trace_id() -> str:
    """生成 trace id（16 位十六进制），便于人工检索"""
    return uuid.uuid4().hex[:16]


def set_trace_id(trace_id: str):
    """绑定当前上下文的 trace id，返回用于恢复的 token"""
    return trace_id_var.set(trace_id or "-")


def reset_trace_id(token) -> None:
    """恢复上一个 trace id（请求结束后调用，避免上下文串号）"""
    try:
        trace_id_var.reset(token)
    except ValueError:
        pass


def get_trace_id() -> str:
    return trace_id_var.get()


def set_task_id(task_id: str):
    """绑定当前上下文的后台任务 id，返回用于恢复的 token"""
    return task_id_var.set(task_id or "-")


def reset_task_id(token) -> None:
    try:
        task_id_var.reset(token)
    except ValueError:
        pass


def get_task_id() -> str:
    return task_id_var.get()


class ContextFilter(logging.Filter):
    """把当前上下文的 trace id / task id 注入日志记录（不覆盖显式传入的值）"""

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "trace_id", None):
            record.trace_id = trace_id_var.get()
        if not getattr(record, "task_id", None):
            record.task_id = task_id_var.get()
        return True


_context_filter = ContextFilter()


def _make_formatter() -> logging.Formatter:
    return logging.Formatter(LOG_FORMAT, DATE_FORMAT)


class DailyFileHandler(logging.FileHandler):
    """按天切换的日志文件：写入 logs/app-YYYY-MM-DD.log，跨天自动换新文件。"""

    def __init__(self, log_dir: str, level: int) -> None:
        self._log_dir = log_dir
        self._day = date.today().isoformat()
        super().__init__(os.path.join(log_dir, f"app-{self._day}.log"), mode="a", encoding="utf-8")
        self.setLevel(level)
        self.setFormatter(_make_formatter())
        self.addFilter(_context_filter)
        # 标记本工程挂载的 handler，防止 uvicorn 热重载（模块重新导入）时重复添加
        self._talent_flow = True

    def emit(self, record: logging.LogRecord) -> None:
        day = date.today().isoformat()
        if day != self._day:
            self._day = day
            self.baseFilename = os.path.abspath(os.path.join(self._log_dir, f"app-{day}.log"))
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
    """初始化日志：全量日志（含错误堆栈与业务流水）统一写入当天文件 app-YYYY-MM-DD.log"""
    os.makedirs(LOG_DIR, exist_ok=True)

    daily_file = DailyFileHandler(LOG_DIR, logging.INFO)

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

    # app.audit.* 业务流水：只向 app 根 logger 传播，不再单独写 business.log
    audit_root = logging.getLogger("app.audit")
    audit_root.setLevel(logging.INFO)
    audit_root.propagate = True


def get_logger(name: str = "app") -> logging.Logger:
    """获取业务子 logger（app.xxx），自动向 app 根 logger 传播输出"""
    return logging.getLogger(name if name.startswith("app") else f"app.{name}")


def get_audit_logger(name: str = "audit") -> logging.Logger:
    """获取业务流水 logger（app.audit.xxx），随 app 根 logger 写入当天文件"""
    if name.startswith("app.audit"):
        return logging.getLogger(name)
    return logging.getLogger(f"app.audit.{name}")
