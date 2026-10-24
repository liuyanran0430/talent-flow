from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.common import ApiResponse
from ..schemas.department import DepartmentCreate, DepartmentOut, DepartmentUpdate
from ..services.department_service import DepartmentNotFoundError, DepartmentService

router = APIRouter(prefix="/departments", tags=["departments"])


@router.get("", response_model=ApiResponse[list[DepartmentOut]], summary="部门列表")
def list_departments(db: Session = Depends(get_db)):
    return ApiResponse.ok(DepartmentService(db).list_departments())


@router.post(
    "",
    response_model=ApiResponse[DepartmentOut],
    status_code=status.HTTP_201_CREATED,
    summary="新增部门",
)
def create_department(payload: DepartmentCreate, db: Session = Depends(get_db)):
    try:
        return ApiResponse.ok(DepartmentService(db).create_department(payload))
    except Exception as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"新增失败：{e}")


@router.get("/{dept_id}", response_model=ApiResponse[DepartmentOut], summary="部门详情")
def get_department(dept_id: int, db: Session = Depends(get_db)):
    try:
        return ApiResponse.ok(DepartmentService(db).get_department(dept_id))
    except DepartmentNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "部门不存在")


@router.put("/{dept_id}", response_model=ApiResponse[DepartmentOut], summary="修改部门")
def update_department(dept_id: int, payload: DepartmentUpdate, db: Session = Depends(get_db)):
    try:
        return ApiResponse.ok(DepartmentService(db).update_department(dept_id, payload))
    except DepartmentNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "部门不存在")


@router.delete("/{dept_id}", response_model=ApiResponse[None], summary="删除部门")
def delete_department(dept_id: int, db: Session = Depends(get_db)):
    try:
        DepartmentService(db).delete_department(dept_id)
    except DepartmentNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "部门不存在")
    return ApiResponse.ok(None, message="deleted")
