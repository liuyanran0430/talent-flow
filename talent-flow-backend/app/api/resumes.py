import hashlib
import json
import os
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.candidate import CandidateCreate
from ..schemas.common import ApiResponse
from ..schemas.resume import ParseRequest, UploadResult
from ..services.async_tasks import create_task, execute_task
from ..services.candidate_service import CandidateNotFoundError, CandidateService
from ..services.resume_parser import parse_resume
from ..services.resume_tasks import run_parse
from ..core.logging_config import (
    get_audit_logger,
    get_logger,
    set_request_id,
)

router = APIRouter(prefix="/resumes", tags=["resumes"])

logger = get_logger("resumes")
audit = get_audit_logger("resume")

UPLOAD_DIR = "uploads"
ALLOWED_EXT = {"pdf", "doc", "docx"}
MAX_SIZE = 20 * 1024 * 1024  # 20MB


@router.post(
    "/upload",
    response_model=ApiResponse[UploadResult],
    status_code=status.HTTP_201_CREATED,
    summary="上传简历并新建候选人（内容查重，等待手动开始分析）",
)
async def upload_resume(
    name: str = "",
    job_id: int | None = Form(default=None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXT:
        audit.warning("简历上传拒绝 file=%s 原因=格式不支持 ext=%s", file.filename, ext)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"仅支持 {ALLOWED_EXT} 格式")
    content = await file.read()
    if len(content) == 0:
        audit.warning("简历上传拒绝 file=%s 原因=文件为空", file.filename)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "简历文件内容为空，无法上传")
    if len(content) > MAX_SIZE:
        audit.warning("简历上传拒绝 file=%s 原因=超过20MB size=%s", file.filename, len(content))
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "文件不能超过 20MB")

    # 内容哈希查重：命中则返回已存在候选人 id，走待复核，不重复入库
    resume_hash = hashlib.sha256(content).hexdigest()
    existing_resume = CandidateService(db).find_by_resume_hash(resume_hash)
    if existing_resume:
        logger.info("重复简历命中查重 candidate_id=%s job_id=%s", existing_resume.candidate_id, existing_resume.job_id)
        audit.info(
            "简历上传重复 candidate_id=%s job_id=%s hash=%s",
            existing_resume.candidate_id, existing_resume.job_id, resume_hash[:12],
        )
        return ApiResponse.ok(UploadResult(success=True, candidate_id=existing_resume.candidate_id), message="duplicate")

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    saved_name = f"{uuid.uuid4().hex}.{ext}"
    saved_path = os.path.join(UPLOAD_DIR, saved_name)
    with open(saved_path, "wb") as f:
        f.write(content)

    # 建候选人为"待解析"，name 留待解析后由 LLM 提取写入
    candidate = CandidateService(db).create_candidate(
        CandidateCreate(
            job_id=job_id,
            status="pending",
            resume_path=saved_path,
            resume_hash=resume_hash,
        )
    )
    logger.info("简历上传成功 candidate_id=%s job_id=%s file=%s", candidate.id, job_id, saved_name)
    audit.info(
        "简历上传完成 candidate_id=%s job_id=%s file=%s size=%s hash=%s",
        candidate.id, job_id, saved_name, len(content), resume_hash[:12],
    )
    return ApiResponse.ok(UploadResult(success=True, candidate_id=candidate.id), message="uploaded")


@router.post(
    "/{candidate_id}/analyze",
    response_model=ApiResponse[dict],
    summary="开始解析简历（后台任务：LLM 提取基本信息 + 生成职位匹配建议）",
)
def analyze_resume(
    candidate_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    try:
        cand, proceed = CandidateService(db).mark_parsing(candidate_id)
    except CandidateNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "candidate not found")
    if not proceed:
        return ApiResponse.ok(
            {"candidate_id": candidate_id, "status": "processing"}, message="already parsing"
        )
    job_id = cand.resume.job_id if cand.resume else None
    request_id = create_task(db, "resume_parse")
    # 触发接口属于 LLM 相关接口，绑定 request_id，本次请求的日志与访问日志都带上它
    set_request_id(request_id)
    logger.info("简历解析任务已入队 candidate_id=%s job_id=%s request_id=%s", candidate_id, job_id, request_id)
    audit.info(
        "简历解析触发 candidate_id=%s job_id=%s request_id=%s",
        candidate_id, job_id, request_id,
    )
    # 异步执行解析：后台任务绑定接口返回的 request_id，前端凭该 id 轮询状态
    background_tasks.add_task(
        execute_task,
        request_id,
        lambda: _run_parse_task(candidate_id, request_id),
    )
    return ApiResponse.ok({"candidate_id": candidate_id, "status": "processing", "request_id": request_id})


def _run_parse_task(candidate_id: int, request_id: str) -> dict:
    """后台任务入口：执行简历解析，任务结果返回候选人 id（详情由前端另行拉取）。

    解析失败时抛错以标记任务 failed（候选人已置 review 并带失败说明），前端轮询可提示。
    """
    ok = run_parse(candidate_id, False, request_id=request_id)
    if not ok:
        raise RuntimeError("简历解析失败，请手动补全信息或重试")
    return {"candidate_id": candidate_id}


@router.post(
    "/parse",
    response_model=ApiResponse[dict],
    summary="解析简历文件，返回基本信息与匹配建议（同步）",
)
def parse_resume_file(req: ParseRequest):
    try:
        result = json.loads(parse_resume(req.file_path, []))
    except Exception as e:
        audit.error("简历同步解析失败 file=%s error=%s", os.path.basename(req.file_path), e)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    audit.info("简历同步解析完成 file=%s suggestions=%s", os.path.basename(req.file_path), len(result.get("suggestions") or []))
    return ApiResponse.ok(result)
