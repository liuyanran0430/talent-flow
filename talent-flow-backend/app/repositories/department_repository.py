from ..models.department import Department
from .base import BaseRepository


class DepartmentRepository(BaseRepository):
    """departments 表读写入口。"""

    def list_all(self) -> list[Department]:
        return self.db.query(Department).order_by(Department.id).all()

    def get(self, dept_id: int) -> Department | None:
        return self.db.get(Department, dept_id)

    def add(self, dept: Department) -> None:
        self.db.add(dept)

    def delete(self, dept: Department) -> None:
        self.db.delete(dept)
