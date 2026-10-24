import hashlib
import json
import os
import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ..database import SessionLocal, get_db
from ..models.candidate import Candidate
from ..models.jobfit import JobFit
from ..models.requirement import RequirementItem
from ..schemas.candidate import CandidateCreate
from ..schemas.common import ApiResponse
from ..schemas.resume import ParseRequest, UploadResult
from ..services.candidate_service import CandidateService
from ..services.resume_parser import parse_resume
from ..logging_config import get_logger

router = APIRouter(prefix="/resumes", tags=["resumes"])

logger = get_logger("resumes")

UPLOAD_DIR = "uploads"
ALLOWED_EXT = {"pdf", "doc", "docx"}
MAX_SIZE = 20 * 1024 * 1024  # 20MB


def run_parse(candidate_id: int, preserve_status: bool = False) -> None:
    """后台解析任务：调用 LLM 解析简历，写回基本信息并生成职位匹配建议（jobfits）。

    :param preserve_status: 要求配置变化触发的重算场景下保持原状态（finish 不降级回 review）
    """
    db = SessionLocal()
    try:
        cand = db.get(Candidate, candidate_id)
        if not cand or not cand.resume_path:
            return
        prev_status = cand.status

        # 该职位的要求项（含判定标准），作为匹配依据
        reqs = (
            db.query(RequirementItem)
            .filter(RequirementItem.job_id == cand.job_id)
            .order_by(RequirementItem.id)
            .all()
            if cand.job_id
            else []
        )

        try:
            result = json.loads(parse_resume(cand.resume_path, reqs))
        except Exception as e:
            import logging

            logging.getLogger("uvicorn.error").exception(
                "resume parse failed for candidate %s: %s", candidate_id, e
            )
            if preserve_status and prev_status == "finish":
                cand.status = "finish"
                cand.info = "简历重新解析失败，保留原匹配建议"
            else:
                cand.status = "review"
                cand.info = "简历解析失败，请手动补全信息"
            db.commit()
            return

        basic = result.get("basic") or {}
        if basic.get("name"):
            cand.name = basic["name"]
        if basic.get("phone"):
            cand.phone = basic["phone"]
        if basic.get("email"):
            cand.email = basic["email"]
        if basic.get("experience"):
            cand.experience = basic["experience"]
        if preserve_status and prev_status == "finish":
            cand.status = "finish"
            cand.info = "要求配置变化，已重新计算匹配建议"
        else:
            cand.status = "review"
            cand.info = "简历解析完成"

        # 覆盖式写入匹配建议：先清旧记录，再按名称对齐要求项落库
        if cand.job_id:
            db.query(JobFit).filter(JobFit.candidate_id == cand.id).delete()
            item_by_name = {r.name: r for r in reqs}
            for s in result.get("suggestions") or []:
                item = item_by_name.get(s.get("name"))
                if not item:
                    continue
                db.add(
                    JobFit(
                        candidate_id=cand.id,
                        requirement_item_id=item.id,
                        suggestion=s.get("suggestion") or "证据不足",
                        evidence=s.get("evidence") or "",
                    )
                )
        db.commit()
    finally:
        db.close()


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
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"仅支持 {ALLOWED_EXT} 格式")
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "简历文件内容为空，无法上传")
    if len(content) > MAX_SIZE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "文件不能超过 20MB")

    # 内容哈希查重：命中则返回已存在候选人 id，走待复核，不重复入库
    resume_hash = hashlib.sha256(content).hexdigest()
    existing = db.query(Candidate).filter(Candidate.resume_hash == resume_hash).first()
    if existing:
        logger.info("重复简历命中查重 candidate_id=%s job_id=%s", existing.id, existing.job_id)
        return ApiResponse.ok(UploadResult(success=True, candidate_id=existing.id), message="duplicate")

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
    cand = db.get(Candidate, candidate_id)
    if not cand:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "candidate not found")
    if cand.status == "processing":
        # 僵死自愈：解析超 3 分钟未完成（服务重载/进程被杀导致后台任务丢失），允许重新触发
        elapsed = (datetime.now() - cand.updated_at).total_seconds()
        if elapsed < 180:
            return ApiResponse.ok(
                {"candidate_id": candidate_id, "status": "processing"}, message="already parsing"
            )
        logger.warning("僵死自愈放行重新解析 candidate_id=%s 卡顿时长=%.0fs", candidate_id, elapsed)
    cand.status = "processing"
    cand.info = "正在解析简历"
    db.commit()
    logger.info("触发简历解析 candidate_id=%s job_id=%s", candidate_id, cand.job_id)
    background_tasks.add_task(run_parse, candidate_id)  # 异步执行解析
    return ApiResponse.ok({"candidate_id": candidate_id, "status": "processing"})


@router.post(
    "/parse",
    response_model=ApiResponse[dict],
    summary="解析简历文件，返回基本信息与匹配建议（同步）",
)
def parse_resume_file(req: ParseRequest):
    try:
        result = json.loads(parse_resume(req.file_path, []))
    except Exception as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    return ApiResponse.ok(result)
