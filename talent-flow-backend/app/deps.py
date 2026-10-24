from sqlalchemy.orm import Session

from .database import get_db


def db_session() -> Session:
    """便于 service 层直接获取 session 的便捷函数；接口内仍推荐使用 Depends(get_db)。"""
    return next(get_db())
