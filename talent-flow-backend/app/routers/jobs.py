from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.common import ApiResponse
from ..schemas.job import JobCreate, JobOut, JobUpdate, JobWithStats
from ..services.job_service import JobNotFoundError, JobService

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=ApiResponse[list[JobWithStats]], summary="职位列表")
def list_jobs(
    search: str | None = Query(None, description="按职位名模糊搜索"),
    job_status: str | None = Query(None, alias="status", description="open/urgent/paused/closed"),
    db: Session = Depends(get_db),
):
    items = JobService(db).list_jobs(search=search, status=job_status)
    return ApiResponse.ok(items)


@router.get("/{job_id}", response_model=ApiResponse[JobWithStats], summary="职位详情")
def get_job(job_id: int, db: Session = Depends(get_db)):
    try:
        item = JobService(db).get_job(job_id)
    except JobNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    return ApiResponse.ok(item)


@router.post("", response_model=ApiResponse[JobOut], status_code=status.HTTP_201_CREATED, summary="新建职位")
def create_job(payload: JobCreate, db: Session = Depends(get_db)):
    job = JobService(db).create_job(payload)
    return ApiResponse.ok(JobOut.model_validate(job))


@router.put("/{job_id}", response_model=ApiResponse[JobOut], summary="更新职位")
def update_job(job_id: int, payload: JobUpdate, db: Session = Depends(get_db)):
    try:
        job = JobService(db).update_job(job_id, payload)
    except JobNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    return ApiResponse.ok(JobOut.model_validate(job))


@router.delete("/{job_id}", response_model=ApiResponse[None], summary="删除职位")
def delete_job(job_id: int, db: Session = Depends(get_db)):
    try:
        JobService(db).delete_job(job_id)
    except JobNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    return ApiResponse.ok(None, message="deleted")
