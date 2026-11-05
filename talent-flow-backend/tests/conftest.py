"""pytest 共享 fixture：独立 sqlite 文件库 + TestClient + 依赖覆盖。

说明：
- 必须在导入 app 之前注入 DATABASE_URL，settings 有 lru_cache，只能注入一次。
- sqlite 用临时文件而非 :memory:，因为 :memory: 每连接独立，app.database 引擎、
  后台任务的 SessionLocal、TestClient 需要看到同一份数据。
- 每个测试函数结束后清空全部表，保证用例隔离。
"""

import os
import tempfile
from pathlib import Path

_TMP_DIR = Path(tempfile.mkdtemp(prefix="talentflow_test_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP_DIR / 'test.db').as_posix()}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import event  # noqa: E402

from app.database import Base, SessionLocal, engine, get_db  # noqa: E402
from app.main import app  # noqa: E402


# sqlite 默认不校验外键，与线上 MySQL 行为不一致，会让「job_id 指向不存在的职位」这类
# 用例在本地假通过。这里给每个连接打开外键校验，提前暴露同类问题。
@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):  # noqa: ARG001
    if engine.dialect.name != "sqlite":
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture(scope="session", autouse=True)
def _create_tables():
    from app import models  # noqa: F401  确保所有模型注册到 Base.metadata

    Base.metadata.create_all(bind=engine)
    yield
    engine.dispose()
    # 清理本次会话的临时库文件，避免系统临时目录堆积
    for path in _TMP_DIR.glob("*"):
        try:
            path.unlink()
        except OSError:
            pass
    _TMP_DIR.rmdir()


@pytest.fixture(autouse=True)
def _block_real_llm(monkeypatch):
    """禁止测试意外调用真实 LLM：需要 LLM 的用例必须自己 monkeypatch get_model_client。"""
    import app.services.jd_parser as jd_parser
    import app.services.job_profile as job_profile
    import app.services.qa_classifier as qa_classifier
    import app.services.qa_service as qa_service
    import app.services.resume_parser as resume_parser

    def _blocked(*args, **kwargs):
        raise RuntimeError("测试禁止调用真实 LLM，请用 monkeypatch 替换 get_model_client")

    monkeypatch.setattr(resume_parser, "get_model_client", _blocked)
    monkeypatch.setattr(jd_parser, "get_model_client", _blocked)
    monkeypatch.setattr(qa_service, "get_model_client", _blocked)
    monkeypatch.setattr(qa_classifier, "ModelClient", _blocked)
    monkeypatch.setattr(job_profile, "ModelClient", _blocked)
    yield


@pytest.fixture(autouse=True)
def _clean_tables():
    yield
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db):
    def _override_get_db():
        try:
            yield db
        finally:
            pass  # 生命周期由 db fixture 管理

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
