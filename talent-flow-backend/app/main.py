import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import init_db
from .logging_config import get_logger, setup_logging
from .routers import candidates, departments, jobfits, jobs, logs, matches, requirements, resumes, templates
from .schemas.common import ApiResponse

# 模块导入即初始化：uvicorn --reload 启动/热重载后自动生效，日志写入 logs/ 目录
setup_logging()
access_logger = get_logger("http")

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
]


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


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


@app.middleware("http")
async def access_log_middleware(request: Request, call_next):
    """请求访问日志：写操作全量记录；GET 仅记录非 2xx 或慢请求（>500ms），避免轮询刷屏"""
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        access_logger.exception(
            "%s %s -> 500 (unhandled)", request.method, request.url.path
        )
        raise
    duration_ms = (time.perf_counter() - start) * 1000
    method, path, code = request.method, request.url.path, response.status_code
    if method in ("POST", "PUT", "DELETE", "PATCH") or code >= 400 or duration_ms > 500:
        access_logger.info("%s %s -> %s (%.0fms)", method, path, code, duration_ms)
    if code >= 500:
        access_logger.error("%s %s -> %s", method, path, code)
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