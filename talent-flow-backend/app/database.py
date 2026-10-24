from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


_url = settings.database_url
# SQLite 不支持连接池参数，本地验证时走默认引擎
if _url.startswith("sqlite"):
    engine = create_engine(_url, echo=settings.APP_DEBUG, future=True)
else:
    engine = create_engine(
        _url,
        pool_pre_ping=True,
        pool_recycle=3600,
        pool_size=10,
        max_overflow=20,
        echo=settings.APP_DEBUG,
    )

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401  确保模型被注册

    Base.metadata.create_all(bind=engine)
