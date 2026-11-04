"""通用异步任务：LLM 接口立即返回 request_id，后台执行，前端按 request_id 轮询。

状态流转：pending → running → success / failed。
- 结果与错误统一落库（async_tasks），服务重启后仍可查询；
- 后台任务绑定接口返回的 request_id，日志与 LLM 结构化记录都用该字段追溯；
- 任务异常不向上抛，统一转为 failed 状态，前端轮询时读取 error。
"""

import json
import uuid
from datetime import datetime
from typing import Any, Callable

from sqlalchemy.orm import Session

from ..core.logging_config import get_logger, reset_request_id, set_request_id
from ..database import SessionLocal
from ..models import AsyncTask

logger = get_logger("tasks")


def create_task(db: Session, task_type: str) -> str:
    """创建异步任务并立即提交，返回 request_id（接口随响应返回给前端）。"""
    request_id = uuid.uuid4().hex
    db.add(AsyncTask(request_id=request_id, task_type=task_type, status="pending"))
    db.commit()
    return request_id


def execute_task(request_id: str, fn: Callable[[], Any]) -> None:
    """后台执行任务：写 running → 执行 → success/failed，结果 JSON 化落库。

    :param request_id: 任务标识，同时作为日志与 LLM 结构化记录中的 request_id
    :param fn: 业务函数，返回值需可 JSON 序列化
    """
    request_token = set_request_id(request_id)
    db = SessionLocal()
    try:
        task = db.get(AsyncTask, request_id)
        if not task:
            logger.warning("异步任务不存在 request_id=%s", request_id)
            return
        task.status = "running"
        task.updated_at = datetime.now()
        db.commit()
        logger.info("异步任务开始 request_id=%s type=%s", request_id, task.task_type)
        try:
            result = fn()
            task.status = "success"
            task.result = json.dumps(result, ensure_ascii=False, default=str)
            logger.info("异步任务完成 request_id=%s type=%s", request_id, task.task_type)
        except Exception as e:  # 任务失败转为状态，前端轮询读取 error
            task.status = "failed"
            task.error = str(e)[:2000]
            logger.exception("异步任务失败 request_id=%s type=%s: %s", request_id, task.task_type, e)
        task.updated_at = datetime.now()
        db.commit()
    finally:
        reset_request_id(request_token)
        db.close()


def get_task_status(db: Session, request_id: str) -> dict | None:
    """查询任务状态；result 已从 JSON 还原为对象，前端可直接使用。"""
    task = db.get(AsyncTask, request_id)
    if not task:
        return None
    result = None
    if task.result:
        try:
            result = json.loads(task.result)
        except json.JSONDecodeError:
            result = task.result
    return {
        "request_id": task.request_id,
        "task_type": task.task_type,
        "status": task.status,
        "result": result,
        "error": task.error,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }
