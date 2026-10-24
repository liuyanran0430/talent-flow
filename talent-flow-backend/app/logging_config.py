"""统一日志配置：业务日志与既有 uvicorn.error 日志同时输出到控制台与 logs/ 目录文件。

文件说明：
- logs/app.log     全量日志（INFO 及以上），10MB 轮转，保留 5 份
- logs/errors.log  仅 ERROR 及以上，5MB 轮转，保留 5 份
"""
import logging
import os
from logging.handlers import RotatingFileHandler

# 后端项目根目录（talent-flow-backend/）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, "logs")

LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _make_file_handler(filename: str, level: int, max_bytes: int, backup_count: int) -> RotatingFileHandler:
    handler = RotatingFileHandler(
        os.path.join(LOG_DIR, filename),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
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
    """初始化日志：app.* 业务 logger 与 uvicorn.error（既有代码使用）均落盘"""
    os.makedirs(LOG_DIR, exist_ok=True)

    all_file = _make_file_handler("app.log", logging.INFO, 10 * 1024 * 1024, 5)
    err_file = _make_file_handler("errors.log", logging.ERROR, 5 * 1024 * 1024, 5)

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    console._talent_flow = True

    # app.* 业务日志：控制台 + 双文件
    app_root = logging.getLogger("app")
    app_root.setLevel(logging.INFO)
    app_root.propagate = False
    _ensure_handlers(app_root, [console, all_file, err_file])

    # uvicorn.error：run_parse / generate / recalculate 等既有失败堆栈走此 logger，补挂文件输出
    # （uvicorn 已为其配置控制台输出，只加文件，不重复控制台）
    uvicorn_error = logging.getLogger("uvicorn.error")
    _ensure_handlers(uvicorn_error, [all_file, err_file])


def get_logger(name: str = "app") -> logging.Logger:
    """获取业务子 logger（app.xxx），自动向 app 根 logger 传播输出"""
    return logging.getLogger(name if name.startswith("app") else f"app.{name}")
