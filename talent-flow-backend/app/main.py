import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .core.config import settings
from .database import init_db
from .core.logging_config import (
    get_logger,
    reset_session_id,
    reset_user_id,
    set_session_id,
    set_user_id,
    setup_logging,
)
from .api import candidates, departments, jobfits, jobs, logs, matches, requirements, resumes, tasks, templates
from .schemas.common import ApiResponse

# 模块导入即初始化：uvicorn --reload 启动/热重载后自动生效，日志写入 logs/ 目录
setup_logging()
access_logger = get_logger("http")
lifecycle_logger = get_logger("lifecycle")

# OpenAPI 文档按功能模块分组，与每个 router 的 tags 一一绑定
TAGS_METADATA = [
    {"name": "jobs", "description": "职位管理：职位的增删改查及候选人推进统计"},
    {"name": "departments", "description": "部门管理：部门增删改查，与职位关联"},
    {"name": "requirements", "description": "职位要求项：必备/加分技能、重要程度与判定标准"},
    {"name": "candidates", "description": "候选人管理：人才资料与 AI 匹配分维护"},
    {"name": "resumes", "description": "简历导入：上传简历文件并自动建候选人档案"},
    {"name": "templates", "description": "要求模板：复用招聘标准并一键应用到职位"},
    {"name": "matches", "description": "岗位匹配打分：岗位与候选人的匹配分维护"},
    {"name": "logs", "description": "日志：接收前端上报的异常日志并落盘"},
    {"name": "tasks", "description": "异步任务：LLM 接口返回 request_id，凭该 id 轮询处理状态与结果"},
]


@asynccontextmanager
async def lifespan(_: FastAPI):
    lifecycle_logger.info(
        "应用启动 name=%s env=%s debug=%s", settings.APP_NAME, settings.APP_ENV, settings.APP_DEBUG
    )
    init_db()
    lifecycle_logger.info("数据库初始化完成")
    yield
    lifecycle_logger.info("应用关闭")


app = FastAPI(
    title=settings.APP_NAME,
    description="TalentFlow 招聘后台 API，与前端 talent-flow 对接。功能模块按 OpenAPI tags 划分。",
    version="0.1.0",
    openapi_tags=TAGS_METADATA,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _client_ip(request: Request) -> str:
    """获取真实客户端 IP：优先反向代理头，其次直连地址"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host if request.client else "-"


@app.middleware("http")
async def context_middleware(request: Request, call_next):
    """请求上下文：记录前端会话/用户标识，供 LLM 结构化日志使用。

    request_id 不由 HTTP 请求分配，只有调用 LLM 的异步任务会绑定它（等于接口返回给前端的 request_id）。
    访问日志规则：CORS 预检不记录；写操作全量记录；GET 仅记录非 2xx 或慢请求（>500ms），避免轮询刷屏。
    """
    method = request.method
    if method == "OPTIONS":
        # 预检请求不产生业务行为，跳过上下文绑定与访问日志，避免日志被刷屏
        return await call_next(request)

    session_token = set_session_id(request.headers.get("X-Session-ID"))
    user_token = set_user_id(request.headers.get("X-User-ID"))

    start = time.perf_counter()
    path, client = request.url.path, _client_ip(request)
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.perf_counter() - start) * 1000
        access_logger.exception(
            "%s %s -> 500 (unhandled) client=%s (%.0fms)", method, path, client, duration_ms
        )
        reset_session_id(session_token)
        reset_user_id(user_token)
        raise

    duration_ms = (time.perf_counter() - start) * 1000
    code = response.status_code
    if method in ("POST", "PUT", "DELETE", "PATCH") or code >= 400 or duration_ms > 500:
        access_logger.info(
            "%s %s -> %s client=%s (%.0fms)", method, path, code, client, duration_ms
        )
    if code >= 500:
        access_logger.error("%s %s -> %s client=%s", method, path, code, client)
    reset_session_id(session_token)
    reset_user_id(user_token)
    return response


@app.get("/health", response_model=ApiResponse[dict], tags=["jobs"], summary="健康检查")
def health():
    return ApiResponse.ok({"status": "ok", "env": settings.APP_ENV})


@app.get("/", response_model=ApiResponse[dict], tags=["jobs"], summary="根路径")
def root():
    return ApiResponse.ok(
        {
            "name": settings.APP_NAME,
            "docs": "/docs",
            "redoc": "/redoc",
            "openapi": "/openapi.json",
        }
    )


app.include_router(departments.router)
app.include_router(jobs.router)
app.include_router(requirements.router)
app.include_router(candidates.router)
app.include_router(resumes.router)
app.include_router(jobfits.router)
app.include_router(matches.router)
app.include_router(templates.router)
app.include_router(logs.router)
app.include_router(tasks.router)