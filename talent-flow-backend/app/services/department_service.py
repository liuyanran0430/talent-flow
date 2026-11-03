from sqlalchemy.orm import Session

from ..models.department import Department
from ..repositories import DepartmentRepository
from ..schemas.department import DepartmentCreate, DepartmentUpdate


class DepartmentNotFoundError(Exception):
    pass


class DepartmentService:
    def __init__(self, db: Session):
        self.repo = DepartmentRepository(db)

    def list_departments(self) -> list[Department]:
        return self.repo.list_all()

    def get_department(self, dept_id: int) -> Department:
        d = self.repo.get(dept_id)
        if not d:
            raise DepartmentNotFoundError(f"部门 {dept_id} 不存在")
        return d

    def create_department(self, payload: DepartmentCreate) -> Department:
        d = Department(**payload.model_dump())
        self.repo.add(d)
        self.repo.commit()
        self.repo.refresh(d)
        return d

    def update_department(self, dept_id: int, payload: DepartmentUpdate) -> Department:
        d = self.get_department(dept_id)
        for k, v in payload.model_dump(exclude_unset=True).items():
            setattr(d, k, v)
        self.repo.commit()
        self.repo.refresh(d)
        return d

    def delete_department(self, dept_id: int) -> None:
        d = self.get_department(dept_id)
        self.repo.delete(d)
        self.repo.commit()
