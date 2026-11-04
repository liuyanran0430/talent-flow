# TalentFlow 前端 · 招聘配置中心

基于 React 18 + Vite 5 + Tailwind CSS 的智能招聘中台前端，配合 [talent-flow-backend](../talent-flow-backend) 使用，覆盖「职位 → 要求 → 简历导入 → 候选人 → 匹配看板」的完整招聘配置流程。

- 技术栈：React 18、Vite 5、Tailwind CSS 3、@iconify/react
- 后端 API 地址：`http://localhost:8080`（硬编码在各页面中，启动前请先启动后端）

---

## 一、核心能力

| 模块 | 能力说明 |
| --- | --- |
| 职位管理 | 部门与职位的增删改查；按部门/状态/关键词筛选与分页；维护招聘人数、状态（招聘中/已暂停/已关闭）与职位 JD |
| 职位要求配置 | 选择部门/职位后维护「必须/加分」要求项（名称、重要程度、判定标准）；支持**调用后端 LLM 从 JD 一键生成要求项**（先预览编辑，再批量覆盖写入）；支持要求模板的创建、编辑、应用到职位；要求变更后可一键触发该职位候选人重算 |
| 导入简历 | 拖拽上传 PDF/DOC/DOCX（单文件 ≤ 20MB），按内容哈希自动查重；导入队列管理，可逐个或批量「开始分析」；实时轮询解析状态；预览/编辑候选人基本信息与逐项匹配建议 |
| 候选人管理 | 候选人搜索、按职位/状态筛选、分页；详情弹窗查看与编辑资料、状态；维护匹配建议（满足/不满足/证据不足 + 匹配依据）；重新计算并保存匹配得分；删除候选人 |
| 职位匹配看板 | 按职位查看候选人匹配概览、得分与关键结论（命中/加分/待核实/待补强）；匹配算法参数（权重、必备项门槛、推荐阈值）可调整并持久化到 `localStorage` |
| 可观测性 | 前端分级日志（内存环形缓冲 `window.__TALENT_LOGS__`）；`warn`/`error` 与未捕获异常自动上报后端 `POST /logs/frontend`，携带会话 id、页面、URL、UA 与堆栈 |

### 日志与追溯

- 会话 id 保存在 `sessionStorage` 的 `talent-flow-session-id`，同一标签页会话内稳定，可通过 `logger.sessionId` 或 `window.__TALENT_SESSION_ID__` 查看；
- 页面切换会记录 `nav` info 日志（仅控制台，不上报），当前页面同步到 `window.__TALENT_SECTION__`；
- `warn`/`error` 日志（含全局未捕获异常、未处理 Promise 拒绝、错误 Toast）自动上报后端，`keepalive` 保证页面卸载时尽力发出；
- 接口失败（非 2xx / 网络错误）由 `apiFetch` 自动派发 `talent:api-error`，logger 用当前 `request_id` 记录，前后端同一次 LLM 请求的 `request_id` 完全一致；
- 所有接口经 `src/utils/api.js` 的 `apiFetch` 自动带上 `X-Session-ID` 请求头（会话 id 定义在 `src/utils/requestContext.js`）；
- `request_id` 只有调用 LLM 的异步接口才有：接口返回后由页面调用 `setActiveRequestId` 写入上下文，期间前端日志都带上它，任务结束自动清除；
- 控制台日志前缀为 `[时间][request_id][tag]`，无 request_id 时显示 `-`；内存缓冲 `window.__TALENT_LOGS__` 的条目同样包含 `request_id`；
- 当前可查看 `window.__TALENT_REQUEST_ID__`（活跃的 LLM 请求 id）与 `window.__TALENT_SESSION_ID__`（会话 id）；
- 排障时用该 `request_id` 在后端 `logs/app-YYYY-MM-DD.log` 与 `logs/llm-YYYY-MM-DD.log` 检索，在 `logs/frontend-YYYY-MM-DD.log` 检索同一次操作的前端报错（含 `request_id` 字段），两侧用同一个 id 对齐；
- 前端日志在后端 `frontend-YYYY-MM-DD.log` 中按 `session_id` 串联，可还原同一用户会话的操作路径。

### 匹配得分算法

代码位置：[matchScore.js](file:///e:/AI全栈/workspace/talent-flow/talent-flow-web/src/utils/matchScore.js)

1. 单项得分：满足 = 1，证据不足 = 0.5，不满足 = 0
2. 基础分 = 100 × Σ(权重 × 单项得分) / Σ权重，仅统计「必须」项，权重按重要程度（默认 高 45 / 中 35 / 低 20）
3. 必备项满足率低于门槛（默认 80%）时，分数封顶为推荐阈值 - 1
4. 加分项每满足一项 +2 分，最多 +6 分，总分封顶 100

算法设置保存在 `localStorage` 的 `talent-flow-algo-settings` 键中。

---

## 二、项目目录

```
talent-flow-web/
├── index.html               # 入口 HTML
├── package.json             # 依赖与脚本
├── vite.config.js           # Vite 配置（端口 3001）
├── tailwind.config.js       # Tailwind 扫描范围
├── postcss.config.js        # Tailwind + autoprefixer
├── src/
│   ├── main.jsx             # React 挂载入口，初始化全局异常捕获
│   ├── App.jsx              # 应用外壳 + 侧栏抽屉 + 移动顶栏 + 页面切换
│   ├── index.css            # 全局样式（Tailwind 指令）
│   ├── components/
│   │   ├── Sidebar.jsx      # 左侧导航（桌面静态 + 移动端抽屉，navigate 自动收起）
│   │   ├── Header.jsx       # 桌面顶部面包屑与用户区（md 断点以上显示）
│   │   ├── MobileHeader.jsx # 移动端顶栏（md 断点以下显示，含汉堡按钮）
│   │   ├── Modal.jsx        # 通用弹窗（移动端全屏、桌面居中）
│   │   ├── Icon.jsx         # Iconify 图标封装
│   │   └── CandidateBlocks.jsx  # 候选人公共展示组件（JobfitTable + AiAnalysisBlock）
│   ├── context/
│   │   └── AppContext.jsx   # 全局状态：当前页面、Toast、导入队列、抽屉开关、navigate
│   ├── pages/
│   │   ├── Jobs.jsx         # 职位管理（表格 + 移动端卡片列表）
│   │   ├── Requirements.jsx # 职位要求配置（含 AI 一键生成 + JD 重算）
│   │   ├── ImportResume.jsx # 导入简历（队列 + 预览 + 候选人编辑弹框）
│   │   ├── Candidates.jsx   # 候选人管理（卡片列表 + 详情/编辑弹框）
│   │   └── Report.jsx       # 职位匹配看板（候选概览 + 维度分析侧栏）
│   └── utils/
│       ├── matchScore.js    # 匹配得分算法 + 分数 upsert（持久化 localStorage）
│       └── logger.js        # 分级日志 + 会话 id + 环形缓冲 + 后端 /logs/frontend 上报
└── dist/                    # npm run build 产物（可重新生成，gitignore）
```

---

## 三、依赖说明

### 运行环境

- Node.js **18 及以上**（Vite 5 要求）
- npm 9 及以上（或使用 pnpm/yarn）

### 生产依赖

| 依赖 | 用途 |
| --- | --- |
| `react` / `react-dom` 18 | UI 框架 |
| `@iconify/react` | Solar 图标集（运行时从 Iconify 拉取图标数据，需要网络） |

### 开发依赖

| 依赖 | 用途 |
| --- | --- |
| `vite` 5 / `@vitejs/plugin-react` | 开发服务器与构建 |
| `tailwindcss` 3 / `postcss` / `autoprefixer` | 原子化样式与构建管线 |

---

## 四、启动方式

### 1. 安装依赖

```bash
cd talent-flow-web
npm install
```

> 首次安装会依据 `package-lock.json` 安装；如网络较慢，可切换 npm 镜像后重试。

### 2. 先启动后端

前端所有请求都指向 `http://localhost:8080`，请先按 [后端 README](../talent-flow-backend/README.md) 启动 API 服务，否则页面会提示「加载失败」。

### 3. 启动开发服务器

```bash
npm run dev
```

- 默认地址：`http://localhost:3001`
- `vite.config.js` 中 `server.open: true`，启动后会自动打开浏览器
- 端口被占用时修改 [vite.config.js](file:///e:/AI全栈/workspace/talent-flow/talent-flow-web/vite.config.js) 的 `server.port`；若改动端口，请同步后端 `.env` 的 `FRONTEND_ORIGIN`（CORS 白名单）

### 4. 生产构建与预览

```bash
npm run build     # 产物输出到 dist/
npm run preview   # 本地预览构建产物，默认 http://localhost:4173
```

部署 `dist/` 到静态服务器时，需保证该页面能访问到后端 `http://localhost:8080`。

### 快速验证

1. 打开 `http://localhost:3001`，左侧出现 5 个菜单且无报错；
2. 进入「职位管理」，列表能加载（说明后端 `/jobs` 正常）；
3. 进入「导入简历」，可上传 PDF 并观察解析状态。

---

## 五、后端接口依赖（速查）

前端使用的后端接口（详见后端 `/docs`）：

- `/departments`、`/jobs`
- `/requirements/{job_id}/items`、`/requirements/{job_id}/generate`、`/requirements/{job_id}/items/batch`、`/requirements/{job_id}/recalculate`
- `/templates`、`/templates/{id}/apply`
- `/resumes/upload`、`/resumes/{candidate_id}/analyze`
- `/candidates`、`/candidates/{id}`
- `/jobfits/candidates/{candidate_id}`、`/jobfits/{id}`
- `/matches/candidates/{candidate_id}`、`/matches`
- LLM 相关异步接口：`POST /requirements/{job_id}/generate`、`POST /requirements/{job_id}/recalculate`、`POST /resumes/{candidate_id}/analyze` 立即返回 `request_id`，前端用 `GET /tasks/{request_id}` 轮询至 `success/failed`；轮询封装见 `src/utils/api.js` 的 `pollTask`
- `/logs/frontend`

> API 基址硬编码为 `http://localhost:8080`（部分页面使用 `const API_BASE`，部分直接写完整 URL）。若后端端口变化，需要同时修改 `src/pages/` 下的 5 个页面与 `src/utils/logger.js`、`src/utils/matchScore.js`，共 7 个文件。

---

## 六、常见问题

| 现象 | 排查方向 |
| --- | --- |
| 页面数据为空、Toast 提示「加载失败」 | 后端未启动或端口不是 8080；浏览器控制台查看 CORS 报错，确认后端 `FRONTEND_ORIGIN` 与前端地址一致 |
| 图标不显示 | `@iconify/react` 需要访问 Iconify CDN，检查网络/代理 |
| 简历上传失败（400） | 仅支持 pdf/doc/docx，文件不能为空且 ≤ 20MB；重复简历会返回 `message=duplicate` |
| 解析一直停留在「解析中」 | 后端 LLM 未配置或调用超时；后端超过 3 分钟会自动允许重新解析，也可重试「开始分析」；用接口返回的 `request_id` 在 `logs/app-YYYY-MM-DD.log` 与 `logs/llm-YYYY-MM-DD.log` 查看解析进度与模型调用明细 |
| 端口冲突 | 修改 `vite.config.js` 的 `server.port`，并同步后端 `FRONTEND_ORIGIN` |
