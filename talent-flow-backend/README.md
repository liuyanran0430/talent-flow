# TalentFlow Backend

TalentFlow 智能招聘中台的后端服务，基于 **FastAPI + SQLAlchemy 2.0 + MySQL**，与前端 `../talent-flow`（React 18 + Vite）对接。

核心能力：

- 部门 / 职位 / 候选人管理（CRUD + 分页 + 筛选）
- 职位要求项配置，支持 **LLM 基于 JD 自动生成要求项**（`jd_parser.py`）
- 简历上传与 **LLM 简历解析**（`resume_parser.py`）：提取基本信息 + 按职位要求项生成匹配建议（满足 / 不满足 / 证据不足 + 匹配依据）
- 岗位匹配打分（matches）与匹配建议（jobfits）维护
- 要求项模板：复用招聘标准并一键应用到职位

LLM 通过 LangChain LCEL 编排（preprocess → classify → validate），使用 OpenAI 兼容接口（默认配置为阿里云 DashScope `qwen-max`，可换任意兼容服务）。

## 目录结构

```
talent-flow-backend/
├── app/
│   ├── main.py              # FastAPI 入口：CORS、OpenAPI tags、路由挂载、/health
│   ├── config.py            # 配置（pydantic-settings，读取 .env）
│   ├── database.py          # SQLAlchemy 引擎、SessionLocal、Base、init_db（启动自动建表）
│   ├── deps.py              # 依赖注入工具
│   ├── models/              # ORM 模型（8 张表）
│   │   ├── department.py    # departments 部门
│   │   ├── job.py           # jobs 职位
│   │   ├── candidate.py     # candidates 候选人
│   │   ├── requirement.py   # requirement_items 职位要求项
│   │   ├── template.py      # requirement_templates / template_items 要求模板
│   │   ├── jobfit.py        # jobfits 匹配建议（候选人 × 要求项）
│   │   └── match.py         # matches 岗位匹配打分（职位 × 候选人）
│   ├── schemas/             # Pydantic 请求/响应模型（common.py 为统一封装）
│   ├── routers/             # 路由层（每个文件一个 OpenAPI tag）
│   │   ├── departments.py   # 部门 CRUD
│   │   ├── jobs.py          # 职位 CRUD
│   │   ├── requirements.py  # 要求项管理 + JD 生成
│   │   ├── candidates.py    # 候选人 CRUD
│   │   ├── resumes.py       # 简历上传 / 解析触发
│   │   ├── jobfits.py       # 匹配建议维护
│   │   ├── matches.py       # 匹配打分维护
│   │   └── templates.py     # 要求模板管理与应用
│   └── services/            # 业务逻辑层
│       ├── *_service.py     # 各实体 CRUD / 统计
│       ├── jd_parser.py     # LLM：JD → 要求项列表
│       └── resume_parser.py # LLM：简历 → 基本信息 + 匹配建议
├── scripts/
│   └── export_openapi.py    # 导出 OpenAPI 文档（yaml/json）
├── uploads/                 # 简历文件存储（运行时生成）
├── requirements.txt
├── .env.example
└── README.md
```

## 快速开始

```bash
# 1. 创建虚拟环境并安装依赖（Python 3.10+）
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # Windows PowerShell
pip install -r requirements.txt

# 2. 安装 LLM 解析依赖（resume_parser / jd_parser 需要）
pip install langchain langchain-openai pypdf python-docx

# 3. 准备 MySQL（utf8mb4）
mysql -uroot -p -e "CREATE DATABASE IF NOT EXISTS talent_flow CHARACTER SET utf8mb4;"

# 4. 配置环境变量
copy .env.example .env
#   编辑 .env：填写 DB_PASSWORD，并追加 LLM 配置（见下表）

# 5. 启动（首次启动 init_db() 自动建表）
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 6. 访问
#   Swagger:  http://localhost:8000/docs
#   ReDoc:    http://localhost:8000/redoc
#   健康检查: http://localhost:8000/health
```

## 环境变量

| 变量 | 说明 | 示例 |
| --- | --- | --- |
| `APP_NAME` / `APP_ENV` / `APP_DEBUG` | 应用名 / 环境 / 调试开关 | `TalentFlow Backend` / `dev` / `true` |
| `DB_HOST` / `DB_PORT` | MySQL 地址 | `127.0.0.1` / `3306` |
| `DB_USER` / `DB_PASSWORD` | MySQL 账号 | `root` / `******` |
| `DB_NAME` | 数据库名 | `talent_flow` |
| `DATABASE_URL` | 可选，直接覆盖连接串（本地可用 SQLite 调试） | `sqlite:///./local.db` |
| `FRONTEND_ORIGIN` | 前端地址，多个逗号分隔（CORS 白名单） | `http://localhost:5173` |
| `LLM_MODEL` | 模型名 | `qwen-max` |
| `OPENAI_API_KEY` | LLM 服务 API Key | `sk-xxx` |
| `OPENAI_API_BASE` | OpenAI 兼容接口地址 | `https://dashscope.aliyuncs.com/compatible-mode/v1` |

## API 一览

所有响应统一包裹为 `{ "code": 0, "message": "ok", "data": ... }`；列表接口分页返回 `{ total, page, page_size, items }`。

| 模块 | 主要端点 |
| --- | --- |
| 部门 `departments` | `GET /departments`、`POST /departments`、`PUT /departments/{id}`、`DELETE /departments/{id}` |
| 职位 `jobs` | `GET /jobs`（分页、状态/部门/搜索筛选）、`GET/POST/PUT/DELETE /jobs/{id}` |
| 要求项 `requirements` | `GET /requirements/{job_id}/items`、`POST /requirements/{job_id}/generate`（LLM 生成）、`POST /requirements/{job_id}/items`、`PUT/DELETE /requirements/{job_id}/items/{item_id}` |
| 候选人 `candidates` | `GET /candidates`（分页、搜索、status/job_id 筛选）、`GET/PUT/DELETE /candidates/{id}`、`POST /candidates` |
| 简历 `resumes` | `POST /resumes/upload`（查重 + 建 pending 候选人）、`POST /resumes/{id}/analyze`（后台 LLM 解析）、`POST /resumes/parse`（同步解析） |
| 匹配建议 `jobfits` | `GET /jobfits/candidates/{candidate_id}`、`POST /jobfits`、`PUT/DELETE /jobfits/{id}` |
| 匹配打分 `matches` | `GET /matches/candidates/{candidate_id}`、`POST /matches`、`PUT/DELETE /matches/{id}` |
| 模板 `templates` | `GET/POST /templates`、`GET/PUT/DELETE /templates/{id}`、`POST /templates/{id}/apply`、`POST /templates/{id}/items` |
| 系统 | `GET /health`、`GET /` |

## 简历导入流程（与前端导入简历页对接）

```
上传 POST /resumes/upload
  ├─ SHA256 内容查重：命中 → 返回 duplicate + 已存在候选人 id
  └─ 新建候选人：status = pending（待解析），name 置空，简历存 uploads/
        │
点击「开始分析」POST /resumes/{id}/analyze
  └─ status = processing，后台任务调用 LLM：
       提取基本信息（姓名/电话/邮箱/工作年限）
       按该职位要求项逐项生成匹配建议（满足/不满足/证据不足 + 依据）→ 覆盖写入 jobfits
  ├─ 失败兜底：status = review + info 提示手动补全
  └─ 僵死自愈：processing 超 3 分钟允许重新触发
        │
解析完成 status = review（待确认）→ 前端「确认」后 status = finish
```

候选人状态：`pending`（待解析）→ `processing`（解析中）→ `review`（待确认）→ `finish`（已确认）；`recommended / interview / hired / rejected` 预留给后续招聘流程推进。

## 匹配打分算法（前端计算后写入 matches）

- 基本项按重要程度加权（高 45 / 中 35 / 低 20）：满足 = 1、证据不足 = 0.5、不满足 = 0
- 必备项满足率低于门槛（默认 80%）时，总分封顶在推荐阈值以下
- 加分项每满足一项 +2 分（上限 +6），总分封顶 100
- matches 表同时记录基本项满足 / 不满足 / 证据不足个数与加分项满足个数，供分析页统计

## 数据模型要点

- `candidates.resume_hash`：简历内容 SHA256，唯一索引，用于上传查重
- `candidates.resume_path`：简历在 `uploads/` 下的存储路径；删除候选人时级联清理 jobfits 并删除文件
- `jobfits`：候选人 × 要求项的匹配结果（suggestion + evidence），解析时覆盖式重建
- `matches`：职位 × 候选人的打分记录（score 0-100 + 各类匹配项计数）
- `requirement_items.type`：`必须` / `加分`；`importance`：`高` / `中` / `低`
- `jobs.status`：`open`（招聘中）/ `paused`（已暂停）/ `closed`（已关闭），要求配置与简历导入仅针对 open 职位

## 重新生成 OpenAPI 文档

```bash
.\.venv\Scripts\python.exe scripts\export_openapi.py                   # 默认 -> openapi.yaml
.\.venv\Scripts\python.exe scripts\export_openapi.py -o openapi.json   # -> openapi.json
```

## 与前端联调

前端项目位于 `../talent-flow`（Vite 默认端口 5173），所有页面数据均来自本服务真实接口，全局 API 地址在前端各页面顶部的 `API_BASE` 常量（默认 `http://localhost:8000`）。启动顺序：MySQL → 本服务（8000）→ 前端 dev server。
