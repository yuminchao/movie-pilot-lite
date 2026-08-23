# movie-pilot-lite 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or **superpowers:executing-plans** to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 构建独立的单用户自托管网站，实现 M-Team 搜索、qBittorrent 推送、任务状态、加密配置和 Docker 交付。

**Architecture:** FastAPI 后端负责认证、SQLite、第三方请求和凭据解密；React/Vite 前端只调用业务 API。M-Team 与 qBittorrent 通过独立适配器隔离，下载记录只读展示，不提供删除操作。

**Tech Stack:** Python 3.12、FastAPI、Pydantic、SQLAlchemy、Alembic、httpx、argon2-cffi、cryptography、pytest；React、TypeScript、Vite、Vitest；Docker Compose。

---

### Task 1: 初始化工具链

**Files:** `pyproject.toml`, `uv.lock`, `backend/app/main.py`, `backend/tests/test_health.py`, `frontend/package.json`, `frontend/tsconfig.json`, `frontend/vite.config.ts`, `.gitignore`

- [ ] **Step 1: 写失败测试**

```python
def test_health_returns_ok(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2:** 运行 `uv run --project . pytest backend/tests/test_health.py -q`，预期因 `app.main` 不存在而失败。
- [ ] **Step 3:** 创建 FastAPI 应用、依赖清单和 React/Vite 骨架；`GET /api/health` 返回 `{"status":"ok"}`。
- [ ] **Step 4:** 运行同一测试，预期 PASS。
- [ ] **Step 5:** 提交 `git add .; git commit -m "20260823211000 feat 初始化 movie-pilot-lite 工具链"`。

### Task 2: SQLite 和加密配置

**Files:** `backend/app/config/settings.py`, `backend/app/config/crypto.py`, `backend/app/config/repository.py`, `backend/app/db/base.py`, `backend/app/db/models.py`, `backend/app/db/session.py`, `backend/alembic/versions/0001_initial.py`, `backend/tests/test_crypto.py`, `backend/tests/test_config_repository.py`

- [ ] **Step 1: 写失败测试**

```python
def test_encrypt_decrypt_round_trip(crypto):
    ciphertext = crypto.encrypt("tp=secret; uid=42")
    assert ciphertext != "tp=secret; uid=42"
    assert crypto.decrypt(ciphertext) == "tp=secret; uid=42"

def test_each_encryption_uses_new_nonce(crypto):
    assert crypto.encrypt("same") != crypto.encrypt("same")
```

- [ ] **Step 2:** 运行 `uv run --project . pytest backend/tests/test_crypto.py backend/tests/test_config_repository.py -q`，预期失败。
- [ ] **Step 3:** 用 Argon2id 从管理员密码派生 32 字节密钥，用 AES-256-GCM 加密；密文携带版本、salt、nonce；篡改时抛 `InvalidSecret`。实现 `AppConfig`、`AdminUser`、`Session`、`DownloadRecord` 和 Alembic 初始迁移。固定 key 仅允许 `mteam.connection`、`qbittorrent.connection`、`download.defaults`。
- [ ] **Step 4:** 运行测试，预期 PASS；API 层只能得到掩码状态，不能得到解密值。
- [ ] **Step 5:** 提交 `git add backend; git commit -m "20260823211100 feat 增加加密配置与 SQLite 持久化"`。

### Task 3: 管理员认证和会话

**Files:** `backend/app/auth/passwords.py`, `backend/app/auth/session.py`, `backend/app/api/auth.py`, `backend/app/main.py`, `backend/tests/test_auth_api.py`

- [ ] **Step 1: 写失败测试**

```python
def test_setup_then_login(client):
    assert client.post("/api/auth/setup", json={"password": "correct horse battery"}).status_code == 201
    response = client.post("/api/auth/login", json={"password": "correct horse battery"})
    assert response.status_code == 204
    assert "session" in response.cookies

def test_protected_endpoint_requires_session(client):
    assert client.get("/api/settings/mteam").status_code == 401
```

- [ ] **Step 2:** 运行 `uv run --project . pytest backend/tests/test_auth_api.py -q`，预期失败。
- [ ] **Step 3:** 首次只允许 setup；密码用 Argon2id 哈希；登录创建随机会话 ID，保存服务端 session，设置 HttpOnly/SameSite=Lax Cookie；实现 `require_session` 依赖和 60 秒 10 次限流。
- [ ] **Step 4:** 运行测试，预期 PASS。
- [ ] **Step 5:** 提交 `git add backend/app/auth backend/app/api/auth.py backend/tests; git commit -m "20260823211200 feat 增加管理员会话认证"`。

### Task 4: M-Team 适配器和搜索

**Files:** `backend/app/integrations/mteam.py`, `backend/app/services/search.py`, `backend/app/api/search.py`, `backend/tests/test_mteam_client.py`, `backend/tests/test_search_api.py`

- [ ] **Step 1: 写 mock HTTP 失败测试**

```python
def test_search_maps_movie_result(mteam_client, httpx_mock):
    httpx_mock.post("https://m-team.test/api/torrent/search", json={"data": {"data": [{"id": "7", "name": "Movie", "category": "401", "size": 1000, "status": {"seeders": 8, "discount": "FREE"}}]}})
    result = mteam_client.search("Movie", "movie", 1)[0]
    assert result.title == "Movie"
    assert result.category == "movie"
    assert result.download_factor == 0
```

- [ ] **Step 2:** 运行 `uv run --project . pytest backend/tests/test_mteam_client.py backend/tests/test_search_api.py -q`，预期失败。
- [ ] **Step 3:** 实现 `MTeamClient.search` 和 `get_download_url`；合并 Header/Cookie/User-Agent；调用搜索和临时下载接口；电影/电视剧/音乐使用固定分类映射，未知分类归 `all`；15 秒超时和脱敏 `IntegrationError`。
- [ ] **Step 4:** 实现 `GET /api/search`，校验 q、category、page、sort，返回统一结果、分页和短期 `source_token`，不返回凭据或完整下载 URL。
- [ ] **Step 5:** 运行测试，预期 PASS 且无真实网络。
- [ ] **Step 6:** 提交 `git add backend; git commit -m "20260823211300 feat 增加 M-Team 分类搜索"`。

### Task 5: qBittorrent 推送和任务查询

**Files:** `backend/app/integrations/qbittorrent.py`, `backend/app/services/downloads.py`, `backend/app/api/downloads.py`, `backend/app/db/models.py`, `backend/alembic/versions/0002_download_records.py`, `backend/tests/test_qbittorrent_client.py`, `backend/tests/test_downloads_api.py`

- [ ] **Step 1: 写失败测试**

```python
def test_add_download_is_idempotent(client, qb_stub):
    payload = {"source_token": "source-7", "category": "movies", "save_path": "/downloads/movies", "start": True}
    assert client.post("/api/downloads", json=payload).status_code == 201
    assert client.post("/api/downloads", json=payload).status_code == 200
    assert qb_stub.add_calls == 1
```

- [ ] **Step 2:** 运行 `uv run --project . pytest backend/tests/test_qbittorrent_client.py backend/tests/test_downloads_api.py -q`，预期失败。
- [ ] **Step 3:** 用 `qbittorrent-api` 实现用户名/密码或 API Key 登录、连接测试、添加任务和任务列表；状态归一化为 `downloading`、`completed`、`paused`、`error`、`unknown`。
- [ ] **Step 4:** 推送服务校验 source token、绝对保存路径和分类；用 `source_id + category + save_path` 做幂等键；成功写 `download_record`，不保存完整临时 URL。
- [ ] **Step 5:** `GET /api/downloads` 合并本地记录与 qB 实时状态，qB 不可达时返回 `stale=true`；不创建 DELETE/move/rename 路由。
- [ ] **Step 6:** 运行测试并提交 `git add backend; git commit -m "20260823211400 feat 增加 qBittorrent 推送与任务查询"`。

### Task 6: 设置 API 和连接测试

**Files:** `backend/app/api/settings.py`, `backend/app/main.py`, `backend/tests/test_settings_api.py`

- [ ] **Step 1: 写失败测试**

```python
def test_settings_are_masked(client):
    assert client.put("/api/settings/mteam", json={"base_url": "https://m-team.test", "headers": {"x-api-key": "secret"}, "cookie": "tp=secret"}).status_code == 200
    body = client.get("/api/settings/mteam").json()
    assert body["configured"] is True
    assert "secret" not in str(body)
```

- [ ] **Step 2:** 运行 `uv run --project . pytest backend/tests/test_settings_api.py -q`，预期失败。
- [ ] **Step 3:** 实现 M-Team/qB DTO、URL/端口/Header/timeout 校验；保存时加密；GET 只返回 configured、掩码和更新时间；POST test 解密后调用适配器并返回脱敏结果。
- [ ] **Step 4:** 运行测试，预期 PASS；提交 `git add backend; git commit -m "20260823211500 feat 增加 M-Team 与 qB 配置接口"`。

### Task 7: React 主流程

**Files:** `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/styles.css`, `frontend/src/lib/api.ts`, `frontend/src/lib/types.ts`, `frontend/src/features/auth/AuthGuard.tsx`, `frontend/src/features/search/SearchPage.tsx`, `frontend/src/features/settings/SettingsPage.tsx`, `frontend/src/features/downloads/DownloadsPage.tsx`, `frontend/src/App.test.tsx`

- [ ] **Step 1: 写失败测试**

```tsx
it("shows setup or login before protected pages", async () => {
  render(<App />)
  expect(await screen.findByRole("heading", { name: /登录|创建管理员密码/ })).toBeInTheDocument()
})

it("expands result and submits qB options", async () => {
  render(<SearchPage />)
  await userEvent.click(await screen.findByText("流浪地球 2"))
  expect(screen.getByLabelText("保存路径")).toBeVisible()
  await userEvent.click(screen.getByRole("button", { name: "确认推送" }))
  expect(api.post).toHaveBeenCalledWith("/api/downloads", expect.objectContaining({ start: true }))
})
```

- [ ] **Step 2:** 运行 `pnpm --dir frontend test --run`，预期失败。
- [ ] **Step 3:** 实现 API client、认证守卫和搜索页；搜索页提供全部/电影/电视剧/音乐、筛选、排序、分页、空结果/错误状态和行展开推送表单。
- [ ] **Step 4:** 实现设置页和任务页；设置字段掩码，任务页每 5 秒刷新，显示 stale 状态且没有删除按钮。
- [ ] **Step 5:** 实现桌面紧凑表格、移动端两层结果布局、可见焦点、表单 label 和 reduced-motion。
- [ ] **Step 6:** 运行 `pnpm --dir frontend test --run; pnpm --dir frontend build`，预期通过；提交 `git add frontend; git commit -m "20260823211600 feat 增加搜索设置与任务前端"`。

### Task 8: 静态托管和 Docker 验收

**Files:** `Dockerfile`, `docker-compose.yml`, `.env.example`, `docker/healthcheck.py`, `backend/tests/test_static_and_health.py`, `backend/app/main.py`

- [ ] **Step 1: 写失败测试**

```python
def test_health_is_public_and_frontend_fallback_is_served(client):
    assert client.get("/api/health").status_code == 200
    response = client.get("/")
    assert response.status_code == 200
    assert "movie-pilot-lite" in response.text
```

- [ ] **Step 2:** 运行 `uv run --project . pytest backend/tests/test_static_and_health.py -q`，预期失败。
- [ ] **Step 3:** 应用启动创建 `/data` 并执行 Alembic upgrade；若 `frontend/dist` 存在则静态托管并对非 API 路径返回 `index.html`。
- [ ] **Step 4:** Dockerfile 使用 Node 构建阶段和 Python 运行阶段，最终以 UID 10001 非 root 用户启动 Uvicorn；compose 挂载 `./data:/data`，健康检查 `/api/health`，不写入任何秘密。
- [ ] **Step 5:** 运行完整验证，预期测试、前端构建和 compose 配置通过，容器为 healthy，健康检查输出 `ok`，`/data` 保留数据库：

```powershell
uv run --project . pytest backend/tests -q
pnpm --dir frontend test --run
pnpm --dir frontend build
docker compose config
docker compose up --build -d
docker compose ps
docker compose exec movie-pilot-lite python docker/healthcheck.py
docker compose down
```

- [ ] **Step 6:** 提交 `git add .; git commit -m "20260823211700 feat 增加 Docker 部署与健康检查"`。

## 计划自检

- M-Team Header/Cookie、三垂类搜索、结果字段、qB 分类/路径/启动方式、只读任务页、管理员加密配置和 Docker 均有对应任务。
- 所有第三方测试使用 mock，没有真实外网或 qB 请求。
- 前后端共享 `source_token`、`category`、`save_path`、`start`、`qb_hash` 术语。
- 未使用未定义的占位步骤。
