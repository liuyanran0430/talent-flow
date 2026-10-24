from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.common import ApiResponse
from ..schemas.template import (
    ApplyTemplateRequest,
    RequirementTemplateCreate,
    RequirementTemplateOut,
    RequirementTemplateUpdate,
    TemplateItemCreate,
    TemplateItemOut,
    TemplateItemUpdate,
)
from ..services.template_service import (
    TemplateItemNotFoundError,
    TemplateNotFoundError,
    TemplateService,
)

router = APIRouter(prefix="/templates", tags=["templates"])


# 注意：把 /items/{item_id} 类路由声明在 /{template_id} 之前，避免路径歧义
@router.put("/items/{item_id}", response_model=ApiResponse[TemplateItemOut], summary="更新模板要求项")
def update_item(item_id: int, payload: TemplateItemUpdate, db: Session = Depends(get_db)):
    try:
        item = TemplateService(db).update_item(item_id, payload)
    except TemplateItemNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "template item not found")
    return ApiResponse.ok(item)


@router.delete("/items/{item_id}", response_model=ApiResponse[None], summary="删除模板要求项")
def delete_item(item_id: int, db: Session = Depends(get_db)):
    try:
        TemplateService(db).delete_item(item_id)
    except TemplateItemNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "template item not found")
    return ApiResponse.ok(None, message="deleted")


@router.get("", response_model=ApiResponse[list[RequirementTemplateOut]], summary="模板列表")
def list_templates(db: Session = Depends(get_db)):
    return ApiResponse.ok(TemplateService(db).list_templates())


@router.post(
    "",
    response_model=ApiResponse[RequirementTemplateOut],
    status_code=status.HTTP_201_CREATED,
    summary="新建模板（可带要求项一起创建）",
)
def create_template(payload: RequirementTemplateCreate, db: Session = Depends(get_db)):
    try:
        return ApiResponse.ok(TemplateService(db).create(payload))
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


@router.get("/{template_id}", response_model=ApiResponse[RequirementTemplateOut], summary="模板详情（含要求项）")
def get_template(template_id: int, db: Session = Depends(get_db)):
    try:
        item = TemplateService(db).get(template_id)
    except TemplateNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "template not found")
    return ApiResponse.ok(item)


@router.put("/{template_id}", response_model=ApiResponse[RequirementTemplateOut], summary="更新模板基础信息")
def update_template(template_id: int, payload: RequirementTemplateUpdate, db: Session = Depends(get_db)):
    try:
        item = TemplateService(db).update(template_id, payload)
    except TemplateNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "template not found")
    return ApiResponse.ok(item)


@router.delete("/{template_id}", response_model=ApiResponse[None], summary="删除模板")
def delete_template(template_id: int, db: Session = Depends(get_db)):
    try:
        TemplateService(db).delete(template_id)
    except TemplateNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "template not found")
    return ApiResponse.ok(None, message="deleted")


@router.post(
    "/{template_id}/apply",
    response_model=ApiResponse[dict],
    summary="应用模板到职位（把模板项复制为该职位的要求项，usage_count +1）",
)
def apply_template(template_id: int, payload: ApplyTemplateRequest, db: Session = Depends(get_db)):
    try:
        result = TemplateService(db).apply(template_id, payload.job_id)
    except TemplateNotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    return ApiResponse.ok(result, message="applied")


@router.post(
    "/{template_id}/items",
    response_model=ApiResponse[TemplateItemOut],
    status_code=status.HTTP_201_CREATED,
    summary="新增模板要求项",
)
def add_item(template_id: int, payload: TemplateItemCreate, db: Session = Depends(get_db)):
    try:
        item = TemplateService(db).add_item(template_id, payload)
    except TemplateNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "template not found")
    return ApiResponse.ok(item)
