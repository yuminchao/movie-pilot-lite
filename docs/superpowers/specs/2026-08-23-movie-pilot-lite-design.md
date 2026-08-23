# movie-pilot-lite 设计方案

## 1. 产品范围

movie-pilot-lite 是独立于 MoviePilot-3 的单用户、自托管网站，面向家庭服务器或 NAS 使用。第一版提供：

1. 管理员首次创建密码和登录。
2. 配置 M-Team 站点地址、自定义 Header JSON、Cookie 字符串、User-Agent 和请求超时，并测试连接。
3. 配置一个 qBittorrent 实例的地址、端口、用户名、密码或 API Key，并测试连接。
4. 在主界面按“全部、电影、电视剧、音乐”搜索 M-Team 资源。
5. 展示标题、垂类、大小、发布时间、做种数、下载数、促销状态和标签，支持筛选、排序和分页。
6. 为单条结果选择 qB 分类、保存路径和启动方式后推送到 qBittorrent。
7. 查看已推送任务的状态、进度、速度、剩余时间和保存路径。
8. 提供 `Dockerfile` 和 `docker-compose.yml`，通过 `/data` 持久化 SQLite 数据。

第一版不包含多用户、多站点、订阅、自动下载、媒体整理、删除 qB 任务或删除文件。

## 2. 技术方案

采用 FastAPI + React/Vite + SQLite。

后端使用 Python 3.12、FastAPI、Pydantic、SQLAlchemy、Alembic 和 httpx。M-Team 与 qBittorrent 访问集中在后端适配器中，浏览器不直接访问第三方服务，也不接触明文凭据。前端使用 React、TypeScript、Vite 和一个轻量组件层；构建产物由 FastAPI 静态托管，生产环境只运行一个应用容器。

目录结构：

```text
movie-pilot-lite/
├── backend/
│   ├── app/
│   │   ├── api/              HTTP 路由和响应模型
│   │   ├── auth/             管理员认证和会话
│   │   ├── config/           配置读取和加密仓库
│   │   ├── integrations/     M-Team、qBittorrent 客户端
│   │   ├── services/         搜索、推送、任务查询用例
│   │   ├── db/               SQLAlchemy 模型和迁移
│   │   └── main.py           应用入口
│   └── tests/
├── frontend/
│   ├── src/
│   │   ├── app/              路由和应用壳
│   │   ├── features/         auth、search、downloads、settings
│   │   └── components/       表格、表单、状态反馈
│   └── package.json
├── docs/
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

## 3. 数据流和模块边界

```text
浏览器
  │ HttpOnly 会话
  ▼
FastAPI API
  ├─ auth：验证会话和 CSRF
  ├─ settings：解密第三方凭据
  ├─ mteam：搜索、分类映射、生成下载链接
  ├─ qbittorrent：连接、添加任务、查询任务
  └─ downloads：记录推送结果和任务摘要
       │
       ├── M-Team API
       └── qBittorrent Web API
```

M-Team 适配器接收配置化 Header、Cookie、User-Agent 和站点 URL，使用统一的超时、重试和响应校验。搜索结果归一化为内部 `SearchResult`，不把第三方原始响应直接暴露给前端。下载时使用站点返回的临时链接或受控下载地址；后端将其提交给 qBittorrent，并记录 qB 返回的任务 hash。

qBittorrent 适配器支持用户名/密码和 API Key 二选一，连接成功后提供 `add_torrent`、`list_torrents` 和状态归一化能力。第一版不暴露删除、移动、重命名和修改任务设置的接口。

## 4. 认证与敏感数据

- 首次启动无管理员账户时，只允许访问密码创建页面。
- 管理员密码使用 Argon2id 哈希保存。
- 登录成功后创建随机会话 ID，服务端保存会话记录，浏览器只保存 HttpOnly、Secure（HTTPS 时）、SameSite=Lax Cookie。
- 登录和测试连接接口使用 IP/会话级短时限流。
- 使用管理员密码通过 Argon2id 派生独立加密密钥，再用 AES-256-GCM 加密 M-Team Header、Cookie、User-Agent 和 qB 密码/API Key。
- API 只返回 `configured`、掩码和更新时间，不返回敏感字段明文。
- 管理员修改密码时重新加密所有敏感配置；旧密钥只在迁移期间短暂使用。
- 日志中禁止输出 Cookie、Header 值、密码、API Key、完整下载 URL 和 Authorization。
- 所有第三方请求使用固定超时和最大响应体限制，错误信息只返回可脱敏摘要。

## 5. 数据模型

```text
admin_user
  id, password_hash, created_at, last_login_at

session
  id, created_at, expires_at, last_seen_at

app_config
  id, key, encrypted_value, updated_at

download_record
  id, title, source_id, source_url, qb_hash,
  category, save_path, status, error_message,
  created_at, updated_at
```

`app_config` 的 key 只允许代码中的固定枚举值，例如 `mteam.connection`、`qbittorrent.connection` 和 `download.defaults`，禁止任意客户端键名。所有 schema 变更必须配套 Alembic migration。

## 6. API 草案

```text
GET  /api/health
GET  /api/auth/status
POST /api/auth/setup
POST /api/auth/login
POST /api/auth/logout

GET  /api/settings/mteam
PUT  /api/settings/mteam
POST /api/settings/mteam/test
GET  /api/settings/qbittorrent
PUT  /api/settings/qbittorrent
POST /api/settings/qbittorrent/test

GET  /api/search?q=...&category=all|movie|tv|music&page=1&sort=...
POST /api/downloads
GET  /api/downloads
GET  /api/downloads/{id}
```

搜索 API 只返回规范化结果和可用的短期下载标识，不返回 M-Team 凭据。`POST /api/downloads` 在后端重新校验结果标识、生成或获取临时下载地址、执行 qB 推送，并以幂等键防止重复添加。

## 7. 前端设计

主界面采用紧凑结果表：顶部为搜索框和四个垂类入口；下方为筛选、排序、分页和结果表。表格行点击后在行下展开 qB 分类、保存路径、立即开始/暂停选项和确认推送按钮。结果列固定包含标题、垂类、大小、做种、促销、发布时间和推送操作。

设置页分为 M-Team 和 qBittorrent 两个区域，各自提供保存和测试连接；敏感字段显示掩码。下载任务页只读展示任务状态、进度、速度、剩余时间和路径，并显示最近刷新时间与连接错误。

必需状态包括：首次设置、登录失败、连接成功/失败、搜索加载、空结果、站点认证失效、限流、超时、推送成功、qB 不可达、重复任务和任务查询失败。移动端将表格行折叠为标题优先的两层信息，不产生横向滚动。

视觉方向是深色窄导航、浅灰工作区、蓝色主操作色、低圆角和高信息密度，优先可扫描性，不使用营销式 Hero 或装饰性卡片堆叠。

## 8. Docker 交付

Dockerfile 使用多阶段构建：Node 阶段安装前端依赖并执行构建；Python 阶段安装锁定的后端依赖并复制前端产物。最终镜像只启动 Uvicorn，以非 root 用户运行。

`docker-compose.yml`：

- 服务名 `movie-pilot-lite`。
- 端口默认为 `8000:8000`，允许环境变量覆盖。
- `./data:/data` 持久化 SQLite 和会话数据。
- 配置 `TZ`、日志级别、会话有效期和可选代理环境变量。
- 健康检查调用 `/api/health`。
- 不在 compose 文件中写入 M-Team Cookie、Header、qB 密码或管理员密码。

## 9. 测试与验收

后端 pytest 测试不访问真实网络或真实 qB：M-Team 和 qB 客户端在边界 mock。覆盖密码和会话、加密往返、敏感字段不泄露、搜索分类映射、排序筛选、临时下载地址、幂等推送、qB 状态映射、超时和错误响应。

前端测试覆盖登录守卫、设置保存/测试、搜索筛选、结果展开、推送成功/失败和任务轮询。构建检查必须通过 TypeScript 检查、生产构建和容器健康检查。

验收标准：

1. 新容器挂载空 `/data` 后可以完成管理员初始化和登录。
2. 配置并测试 M-Team 后，电影、电视剧、音乐和全部搜索均能显示统一结果模型。
3. 配置并测试 qB 后，任一结果可以带分类、保存路径和启动方式推送成功。
4. 下载任务页能显示刚推送任务的状态和进度，不能执行删除操作。
5. 重启容器后配置、会话策略和下载记录按预期恢复，敏感字段仍不可从 API 读出明文。
6. `docker compose up --build`、后端测试、前端构建和健康检查均通过。
