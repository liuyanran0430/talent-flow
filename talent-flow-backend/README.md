# TalentFlow Backend · 招聘后台 API

基于 FastAPI + SQLAlchemy 的招聘配置后台，为前端 [talent-flow](../talent-flow) 提供部门、职位、职位要求、简历解析、候选人与匹配打分的 REST API；简历解析与 JD 要求生成由 LLM（LangChain LCEL）完成。

- 技术栈：Python 3.10+、FastAPI 0.115、SQLAlchemy 2、Pydantic 2、MySQL 8（可切 SQLite）、LangChain + OpenAI 兼容接口
- 默认监听：`http://localhost:8000`
- 交互式文档：`/docs`（Swagger UI）、`/redoc`

---

## 一、核心能力

| 能力 | 说明 |
| --- | --- |
| 部门/职位管理 | 部门与职位 CRUD；职位列表携带候选人推进统计；按名称/状态筛选 |
| 职位要求项 | 按职位维护「必须/加分」要求项（重要程度、判定标准）；支持**基于 JD 用 LLM 生成要求项**（仅预览，不落库），编辑确认后批量覆盖写入 |
| 简历导入与 AI 解析 | 上传 PDF/DOC/DOCX（≤ 20MB），按 SHA256 内容哈希查重；后台任务用 LLM 提取姓名/电话/邮箱/工作年限，并按职位要求逐项输出「满足/不满足/证据不足 + 匹配依据」；前端轮询候选人状态 |
| 解析结果对齐 | 输出经 Pydantic 结构化校验，并要求建议项与输入要求项按名称一一对齐（遗漏项自动补「证据不足」，多余项剔除） |
| 要求变更重算 | 要求项变化后可异步重算某职位下全部已解析候选人：重新解析生成匹配建议（jobfits），再按算法参数重算得分（matches） |
| 要求模板 | 模板与模板要求项 CRUD，可一键复制模板项到指定职位并累计使用次数 |
| 匹配建议 / 匹配打分 | jobfits（逐项建议）与 matches（0-100 分及各计数项）的查询、新增、更新、删除 |
| 统一响应 | 所有接口返回 `{ code, message, data }`，分页返回 `PageResponse` |
| 日志与可观测性 | 业务日志 + 访问日志统一写入 `logs/app-YYYY-MM-DD.log`（每天一个新文件）；接收前端 `warn/error` 日志落盘 |
| OpenAPI | 路由按 tags 分组，提供 `openapi.yaml` 与一键导出脚本 |

### 匹配打分规则（与前端一致）

单项得分：满足 = 1、证据不足 = 0.5、不满足 = 0；仅「必须」项按重要程度加权（默认 高 45 / 中 35 / 低 20）计算基础分；必备项满足率低于门槛（默认 80%）时封顶在推荐阈值 - 1；加分项每满足一项 +2 分（最多 +6），总分 0-100。

---

## 二、项目目录

```
talent-flow-backend/
├── app/
│   ├── main.py              # FastAPI 实例、CORS、访问日志中间件、路由注册、/health
│   ├── config.py            # pydantic-settings 读取 .env（DB / CORS / DATABASE_URL）
│   ├── database.py          # SQLAlchemy engine、SessionLocal、get_db、init_db（自动建表）
│   ├── deps.py              # 会话便捷函数
│   ├── logging_config.py    # 日志配置（控制台 + 轮转文件）
│   ├── models/              # ORM 模型：部门、职位、要求项、模板、候选人、jobfits、matches
│   ├── schemas/             # Pydantic 请求/响应模型、统一 ApiResponse / 分页
│   ├── routers/             # 各功能模块路由（按 OpenAPI tags 划分）
│   │   ├── departments.py   jobs.py        requirements.py
│   │   ├── candidates.py    resumes.py     jobfits.py
│   │   └── matches.py       templates.py   logs.py
│   └── services/            # 业务服务：简历解析、JD 解析、各实体 CRUD 与重算逻辑
├── scripts/
│   └── export_openapi.py    # 导出 openapi.yaml / openapi.json
├── uploads/                 # 简历上传目录（运行时自动创建，gitignore）
├── logs/                    # app-YYYY-MM-DD.log（运行时按天自动创建，gitignore）
├── openapi.yaml             # 已导出的接口文档
├── requirements.txt         # Python 依赖
├── .env.example             # 环境变量模板
└── .venv/                   # 本地虚拟环境（不入库）
```

### 数据表（`init_db()` 启动时自动 `create_all`）

`departments`、`jobs`、`requirement_items`、`requirement_templates`、`template_items`、`candidates`、`jobfits`、`matches`、`kb_standards`、`llm_runs`、`async_tasks`。无迁移工具，模型变更需自行处理已有库结构；知识库相关变更可用 `python scripts/migrate_kb.py` 幂等补齐。

---

## 三、依赖说明

### 运行环境

- Python **3.10+**（本工程在 3.13 下验证）
- MySQL **8.x**（可选：本地验证可用 SQLite）
- 可访问的 OpenAI 兼容 LLM 接口（如 DeepSeek、通义千问兼容模式），用于简历/JD 解析

### Python 依赖（`requirements.txt`）

| 依赖 | 用途 |
| --- | --- |
| `fastapi` / `uvicorn[standard]` | Web 框架与 ASGI 服务器 |
| `SQLAlchemy` / `PyMySQL` / `cryptography` | ORM 与 MySQL 驱动（cryptography 为 MySQL 认证所需） |
| `pydantic` / `pydantic-settings` | 数据校验与 `.env` 配置 |
| `python-multipart` | 简历文件上传（multipart/form-data） |
| `python-dotenv` | 加载 `.env` |
| `langchain-openai` / `langchain-core` | LCEL 编排、提示词、Pydantic 输出解析 |
| `pypdf` | 提取 PDF 简历文本 |
| `PyYAML` | `scripts/export_openapi.py` 导出 YAML |

> `.docx` 文本提取使用标准库 `zipfile`，无需额外依赖。

---

## 四、配置说明

复制模板并编辑：

```bash
# Windows PowerShell
Copy-Item .env.example .env
# macOS / Linux
cp .env.example .env
```

`.env` 关键项：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `APP_NAME` | `TalentFlow Backend` | 服务名称 |
| `APP_ENV` | `dev` | 运行环境标识（`/health` 返回） |
| `APP_DEBUG` | `true` | 为 `true` 时 SQLAlchemy 会打印 SQL，生产/日常使用建议 `false` |
| `DB_HOST` / `DB_PORT` | `127.0.0.1` / `3306` | MySQL 地址 |
| `DB_USER` / `DB_PASSWORD` | `root` / 空 | MySQL 账号密码 |
| `DB_NAME` | `talent_flow` | 数据库名（**需提前创建**） |
| `DATABASE_URL` | 空 | 可选，直接覆盖连接串；本地快速验证可设为 `sqlite:///./local.db` |
| `FRONTEND_ORIGIN` | `http://localhost:3001` | CORS 白名单，多个用英文逗号分隔 |
| `OPENAI_API_KEY` | 无 | LLM API Key（简历/JD 解析必需） |
| `OPENAI_API_BASE` | 无 | OpenAI 兼容接口地址，如 `https://api.deepseek.com` |
| `LLM_MODEL` | `deepseek-v4-pro` | 模型名（如 `deepseek-v4-flash`、`qwen-max`） |
| `LLM_TIMEOUT` | `120` | 单次请求硬超时（秒），超时视为失败并进入重试 |
| `LLM_MAX_TOKENS` | `4000` | 单次输出 token 上限，配合输入截断防止超出上下文窗口 |
| `LLM_MAX_RETRIES` | `3` | 可重试错误最大重试次数（总尝试 = 1 + 该值），退避 1s/2s/4s |
| `LLM_RETRY_INITIAL_WAIT` / `LLM_RETRY_MAX_WAIT` | `1.0` / `10.0` | 退避起始/单次最长等待秒数 |
| `LLM_RETRY_JITTER` | `0.0` | 退避随机抖动（秒）；0 = 严格 1s/2s/4s |
| `RAG_ENABLED` | `true` | 岗位标准知识库开关；`false` 时检索直接返回空，走纯 LLM |
| `RAG_TOP_K` | `3` | 单次检索注入 Prompt 的标准条目上限 |
| `RAG_MIN_SCORE` | `0.60` | 向量相似度阈值（cosine：`1 - distance`），低于阈值不注入 |
| `EMBEDDING_MODEL` | `text-embedding-v4` | DashScope 向量模型 |
| `EMBEDDING_API_BASE` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | DashScope OpenAI 兼容端点 |
| `EMBEDDING_API_KEY` | 空 | DashScope API Key；为空时知识库仅可维护，检索自动降级 |
| `VECTOR_STORE_BACKEND` | `chroma` | 向量库实现；置为其他值使用空实现（完全禁用检索） |
| `VECTOR_STORE_PATH` | `data/vector_store` | Chroma 本地持久化目录 |
| `RAG_REBUILD_BATCH` | `32` | 全量重建索引时的批量向量化条数 |

> 未配置 LLM 时服务仍可启动，但「生成要求项」「简历解析」会失败。

### LLM 调用错误处理策略

| 问题 | 表现 | 处理策略 |
| --- | --- | --- |
| 429 限流 | 供应商拒绝请求 | 指数退避重试（1s/2s/4s），实现见 `app/llm/client.py` |
| 超时 | 响应迟迟不返回 | `LLM_TIMEOUT` 硬超时 + 重试上限 |
| 上下文超限 | Prompt 过长被拒 | 不重试；预处理阶段截断输入（简历 8000 / JD 6000 / 要求项 4000 字符）+ `LLM_MAX_TOKENS` 输出上限 |
| JSON 解析失败 | 模型输出不合规 | 重试一次（`app/llm/parse_retry.py`）；再失败降级转人工：简历解析置 `review` 待 HR 补全，JD 生成返回错误由 HR 手动填写 |

### 岗位标准知识库（RAG）

方案全文见 `docs/岗位标准知识库方案.md`，这里只列运行操作。

- 存储：MySQL `kb_standards` 为唯一事实源；Chroma 向量索引落在 `data/vector_store/`，可随时重建。
- Embedding：DashScope `text-embedding-v4`（OpenAI 兼容端点），需在 `.env` 配置 `EMBEDDING_API_KEY`。
- 降级：未配置密钥或向量库异常时，检索返回空并记录告警，JD 生成/简历解析自动回退纯 LLM，不阻断主流程。

已有数据库需执行一次迁移（新建 `kb_standards` 表并为 `requirement_items` 加 `standard_id`，幂等可重复执行）：

```bash
python scripts/migrate_kb.py
```

初始化与索引维护：

```bash
# 1. 把历史要求项沉淀为标准草稿（同名/别名自动跳过，分类按规则推断）
curl -X POST http://localhost:8080/kb/import/requirements -H "Content-Type: application/json" -d "{\"limit\": 200}"
# 2. HR 补充判定标准/证据要求后发布（发布即写入向量库）
curl -X POST http://localhost:8080/kb/standards/1/publish
# 3. 全量重建索引（换 embedding 模型或数据迁移后执行）
curl -X POST http://localhost:8080/kb/reindex
# 4. 检索自测
curl "http://localhost:8080/kb/search?q=Python&top_k=5"
```

在线链路：
- JD 生成前用 JD 全文检索已发布标准（Top-K + 相似度阈值 + 名称/别名加权），注入 Prompt 作为参考；
- LLM 回填的 `standard_id` 必须属于本次注入集合，否则置空（防编造来源）；
- 简历解析按 `requirement_items.standard_id` 直接取标准，注入「判定标准 + 证据要求」；
- 命中的标准 id 写入 LLM 结构化日志的 `retrieval_ids`，可回溯判定依据。

---

## 五、启动方式

### 1. 准备数据库（MySQL）

```sql
CREATE DATABASE IF NOT EXISTS talent_flow
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

命令行等价写法：

```bash
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS talent_flow CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

表结构由服务启动时 `Base.metadata.create_all` 自动创建，无需手动执行 SQL。

### 2. 创建虚拟环境并安装依赖

Windows PowerShell：

```powershell
cd talent-flow-backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

macOS / Linux：

```bash
cd talent-flow-backend
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. 配置 `.env`

按上一节填写 MySQL 与 LLM 配置。

### 4. 启动服务

**必须在 `talent-flow-backend/` 目录下启动**（`.env`、`uploads/`、`logs/` 均按当前目录/项目根解析）：

```bash
uvicorn app.main:app --reload --port 8000
# Windows 若未激活虚拟环境或 PowerShell 禁止执行脚本，可直接用：
# .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

启动成功后：

- 健康检查：<http://localhost:8000/health> → `{"code":0,"message":"ok","data":{"status":"ok","env":"dev"}}`
- 接口文档：<http://localhost:8000/docs>

### 5. 启动前端

```bash
cd ../talent-flow
npm install
npm run dev
```

前端默认 `http://localhost:3001`，与后端 `FRONTEND_ORIGIN` 保持一致。

### 可选：不用 MySQL，快速本地验证

在 `.env` 中注释掉 MySQL 配置并添加：

```dotenv
DATABASE_URL=sqlite:///./local.db
```

再执行 `uvicorn app.main:app --reload --port 8000` 即可启动（`database.py` 会自动识别 SQLite 并使用默认连接参数）。`local.db` 已在 `.gitignore` 中忽略。

---

## 六、主要接口

| 模块 | 方法与路径 | 说明 |
| --- | --- | --- |
| 健康检查 | `GET /health`、`GET /` | 服务状态与文档入口 |
| 部门 | `GET/POST /departments`、`GET/PUT/DELETE /departments/{id}` | 部门 CRUD |
| 职位 | `GET/POST /jobs`、`GET/PUT/DELETE /jobs/{id}` | 职位 CRUD，列表含推进统计 |
| 职位要求 | `GET /requirements/{job_id}/items` | 要求项列表 |
| | `POST /requirements/{job_id}/generate` | **异步**调用 LLM 从 JD 生成要求项：立即返回 `request_id`，结果经 `GET /tasks/{request_id}` 获取（仅预览） |
| | `POST /requirements/{job_id}/items/batch` | 批量覆盖写入要求项 |
| | `POST /requirements/{job_id}/items`、`PUT/DELETE /requirements/items/{item_id}` | 单条增改删 |
| | `POST /requirements/{job_id}/recalculate` | **异步**重算该职位候选人（重新解析 + 重算分数），返回 `request_id` |
| 候选人 | `GET /candidates?search=&status=&job_id=&page=&page_size=` | 分页列表（`page_size` 上限 1000） |
| | `GET/POST /candidates`、`GET/PUT/DELETE /candidates/{id}` | 候选人 CRUD / 详情 |
| 简历 | `POST /resumes/upload` | multipart 上传，字段 `file` + 可选 `job_id`；内容查重 |
| | `POST /resumes/{candidate_id}/analyze` | **异步**触发 LLM 解析：立即返回 `request_id`，凭该 id 轮询任务状态 |
| | `POST /resumes/parse` | 同步解析指定本地路径（调试用） |
| 异步任务 | `GET /tasks/{request_id}` | 查询任务状态 `pending/running/success/failed`；成功后 `result` 为业务结果，失败时 `error` 为原因 |
| 匹配建议 | `GET /jobfits/candidates/{candidate_id}`、`POST /jobfits`、`PUT/DELETE /jobfits/{id}` | jobfits CRUD |
| 匹配打分 | `GET /matches/candidates/{candidate_id}`、`POST /matches`、`PUT/DELETE /matches/{id}` | matches CRUD |
| 要求模板 | `GET/POST /templates`、`GET/PUT/DELETE /templates/{id}` | 模板 CRUD（详情含要求项） |
| | `POST /templates/{id}/apply` | 应用模板到职位 |
| | `POST /templates/{id}/items`、`PUT/DELETE /templates/items/{item_id}` | 模板要求项 |
| 日志 | `POST /logs/frontend` | 接收前端 warn/error 日志 |
| 岗位标准知识库 | `GET/POST /kb/standards`、`GET/PUT/DELETE /kb/standards/{id}` | 标准条目 CRUD（`q`/`category`/`status` 过滤） |
| | `POST /kb/standards/{id}/publish`、`POST /kb/standards/{id}/archive` | 发布（写入向量库）/ 归档（移除向量） |
| | `GET /kb/search?q=&top_k=` | 语义检索已发布标准（未配 embedding key 时 `degraded=true`） |
| | `POST /kb/import/requirements` | 历史要求项沉淀为草稿（同名去重） |
| | `POST /kb/reindex` | 全量重建向量索引 |

请求体/响应字段详见 `/docs` 或仓库根目录的 [openapi.yaml](file:///e:/AI全栈/workspace/talent-flow/talent-flow-backend/openapi.yaml)。

### 接口示例

```bash
# 健康检查
curl http://localhost:8000/health

# 上传简历并指定职位
curl -X POST http://localhost:8000/resumes/upload \
  -F "file=@resume.pdf" \
  -F "job_id=1"

# 开始解析
curl -X POST http://localhost:8000/resumes/1/analyze

# 从 JD 生成要求项
curl -X POST http://localhost:8000/requirements/1/generate
```

### 简历导入流程

```
上传 POST /resumes/upload
  ├─ SHA256 内容查重：命中 → 返回 message=duplicate + 已存在候选人 id
  └─ 新建候选人：status=pending，简历存 uploads/
        │
POST /resumes/{id}/analyze
  └─ status=processing，后台任务调用 LLM：
       提取基本信息（姓名/电话/邮箱/工作年限）
       按该职位要求逐项生成匹配建议（满足/不满足/证据不足 + 依据）→ 覆盖写入 jobfits
  ├─ 失败兜底：status=review + info 提示手动补全
  └─ 僵死自愈：processing 超 3 分钟允许重新触发
        │
解析完成 status=review（待确认）→ 前端确认后 status=finish
```

候选人状态：`pending`（待解析）→ `processing`（解析中）→ `review`（待确认）→ `finish`（已确认）；`recommended / interview / hired / rejected` 预留给后续招聘流程推进。

### 数据模型要点

- `candidates.resume_hash`：简历内容 SHA256，唯一索引，用于上传查重；`resume_path` 为 `uploads/` 下的相对路径
- `jobfits`：候选人 × 要求项的匹配结果（`suggestion` + `evidence`），解析时覆盖式重建
- `matches`：职位 × 候选人打分（`score` 0-100 + 各类匹配项计数）
- `requirement_items.type`：`必须` / `加分`；`importance`：`高` / `中` / `低`
- `jobs.status`：`open` / `paused` / `closed`；职位列表接口支持按状态筛选

---

## 七、日志与全流程追溯

### 日志文件

| 路径 | 说明 |
| --- | --- |
| `logs/app-YYYY-MM-DD.log` | 后端全量日志（业务流水、访问日志、错误堆栈），每天一个文件，跨天自动切换 |
| `logs/frontend-YYYY-MM-DD.log` | 前端上报日志（浏览器 warn/error、未捕获异常），与后端日志分开保存 |
| `logs/llm-YYYY-MM-DD.log` | LLM 调用结构化日志，每行一个 JSON，用于排障与用量分析 |
| `uploads/` | 简历文件，使用 UUID 文件名；数据库 `candidates.resume_path` 保存相对路径 |
| `openapi.yaml` | 已导出的接口文档，可通过脚本重新生成 |

不再单独生成 `errors.log` / `business.log` / `uvicorn.err.log`。

每条日志格式：

```
2026-11-03 22:36:37 | INFO    | request_id=- | app.audit.department | 部门创建 id=1 name=日志验证部门
```

### request id（request_id）

- 只有调用 LLM 的接口才有 request_id：接口立即返回该 id（32 位），前端凭它轮询 `GET /tasks/{request_id}` 获取处理状态与结果；
- 后台任务与模型调用绑定同一个 request_id，日志行自动注入 `request_id=`；非 LLM 请求该字段为 `-`；
- 前端通过请求头 `X-Session-ID` 传入会话 id，后端写入日志上下文，供 LLM 结构化日志记录 `session_id`；
- CORS 预检（OPTIONS）不记录访问日志，避免刷屏；
- 访问日志规则：所有写操作（POST/PUT/DELETE/PATCH）全量记录，GET 仅记录非 2xx 或耗时 > 500ms 的请求；
- 访问日志包含方法、路径、状态码、客户端 IP 与耗时。

### LLM 结构化日志（`logs/llm-YYYY-MM-DD.log`）

每次模型调用由 `LLMRunCallbackHandler` 输出一行 JSON，字段与排障问题一一对应：

| 字段 | 内容 | 排障时回答什么问题 |
| --- | --- | --- |
| `request_id` | 本次 LLM 请求唯一标识，与接口返回给前端的一致 | 这次报错对应哪次请求 |
| `user_id` / `session_id` | 用户与会话（当前无登录体系，user_id 为空） | 影响的是谁、哪段对话 |
| `model` / `prompt_version` | 模型与 Prompt 版本（如 `resume_parse/v1`、`jd_generate/v1`） | 当时用的是哪一版 |
| `retrieval_ids` | 命中的知识 chunk（暂未接入 RAG，固定为空数组） | 检索环节召回了什么 |
| `tool_calls` | 工具名与状态码（暂未接入工具调用，固定为空数组） | 外部系统是否正常 |
| `latency_ms` / `prompt_tokens` / `completion_tokens` / `total_tokens` | 耗时与用量 | 慢在哪、贵在哪 |
| `error_type` | 错误分类：`rate_limit` / `timeout` / `connection` / `bad_request` / `server_error` / `unknown` | 是模型错还是工具错 |
| `status` | `success` / `error` | 本次调用是否成功 |

同样的调用明细仍写入 `llm_runs` 表（request_id、model、token、latency、状态、错误信息）。

### 关键业务事件（`app.audit.*`，写入当天文件）

| logger | 记录内容 |
| --- | --- |
| `app.audit.department` / `app.audit.job` | 部门/职位的创建、更新（字段列表）、删除 |
| `app.audit.requirement` | 要求项生成（含项名）、批量覆盖、单条增改删、重算触发/完成（含失败计数） |
| `app.audit.resume` | 上传拒绝原因、重复命中、上传完成（大小/哈希）、解析开始/完成/失败（含建议条数）、同步解析 |
| `app.audit.candidate` | 候选人创建、更新（字段/状态）、删除 |
| `app.audit.template` | 模板创建、应用到职位、删除 |
| `app.audit.jobfit` / `app.audit.match` | 匹配建议、匹配打分的人工新增/更新/删除 |
| `app.audit.frontend` | 前端上报的 warn/error（含 session_id、request_id、页面、URL、UA、堆栈） |

### 后台任务追溯

简历解析与要求重算均为后台任务，统一使用接口返回的 `request_id` 串联：

- 触发接口创建 `async_tasks` 记录并把 `request_id` 立即返回前端；
- 后台任务入口绑定该 `request_id`，期间所有日志行（`request_id=`）与 LLM 结构化日志都用同一个 id；
- 解析进度：`简历解析触发 → 简历解析开始 → 简历解析完成/失败`，同时候选人状态从 `processing` 变为 `review`/`finish`。

### 排障路径

1. 用户反馈问题时，从页面提示或 `GET /tasks/{request_id}` 拿到 `request_id`（前端调试期也可查看 `window.__TALENT_REQUEST_ID__`）；
2. 在 `logs/app-YYYY-MM-DD.log` 中 `grep request_id=<该id>` 得到该次请求的全部业务、访问与错误日志；
3. 在 `logs/llm-YYYY-MM-DD.log` 中按 `request_id` 过滤，查看每次模型调用的 model、prompt_version、耗时、token 与 error_type；
4. 若为前端报错，在 `logs/frontend-YYYY-MM-DD.log` 中按 `session_id` 或 `request_id` 检索前端日志与页面路径；
5. 异常堆栈同样记录在该文件中（`logger.exception` 会带完整堆栈）。

重新导出 OpenAPI：

```bash
python scripts/export_openapi.py                 # 输出 openapi.yaml
python scripts/export_openapi.py -o openapi.json # 输出 JSON
```

---

## 八、注意事项

1. **必须在后端根目录启动**（`uvicorn app.main:app`），否则 `.env` 不会被加载、`uploads/` 相对路径会错位。
2. **`.doc` 旧格式无法解析**：上传接口允许 `doc`，但解析器仅支持 PDF/DOCX/TXT/MD，旧版 `.doc` 会在「开始分析」时失败，建议提前另存为 `.docx` 或 `.pdf`。
3. **解析为异步任务**：`/resumes/{id}/analyze` 立即返回 `request_id` 与 `processing`，前端轮询 `GET /tasks/{request_id}` 拿到 `success/failed`；若服务重启导致任务丢失，超过 3 分钟可重新触发解析（僵死自愈）。
4. **修改要求项不会自动重算已有候选人**，需显式调用 `/requirements/{job_id}/recalculate`。
5. `APP_DEBUG=true` 会输出大量 SQL，日常使用建议置为 `false`。
6. `.env` 含密钥，已在 `.gitignore` 中忽略，请勿提交；`openapi_tmp.json` 为历史调试文件，可忽略。
