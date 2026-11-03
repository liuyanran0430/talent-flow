from sqlalchemy.orm import Session


class BaseRepository:
    """仓储基类：持有 session，统一暴露事务与刷新入口。

    约定：具体写方法只做 add/flush，commit 由 service 编排层在业务边界调用，
    以保证多步写操作（如覆盖式重建）处于同一事务。
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def flush(self) -> None:
        self.db.flush()

    def commit(self) -> None:
        self.db.commit()

    def refresh(self, instance) -> None:
        self.db.refresh(instance)

    def rollback(self) -> None:
        self.db.rollback()
