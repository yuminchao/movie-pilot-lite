# movie-pilot-lite

一个独立、单用户、自托管的 M-Team 搜索与 qBittorrent 下载控制台。

## 功能

- 配置 M-Team 站点地址、自定义 Header JSON、Cookie、User-Agent 和请求超时。
- 配置 M-Team 每日自动签到时间，并查看最近一次签到状态。
- 按全部、电影、电视剧、音乐检索资源。
- 按促销、做种数、发布时间筛选和排序结果。
- 为单条资源覆盖 qBittorrent 分类、保存路径和启动方式。
- 配置默认 qBittorrent 分类、保存路径和启动方式。
- 查看 qBittorrent 任务进度、速度、状态和保存路径。
- 管理员密码登录，敏感配置使用管理员密码派生密钥加密保存。

第一版不提供订阅、自动下载、媒体整理、多用户、多站点或删除任务/文件功能。

## Docker Compose 部署

要求安装 Docker Engine 和 Docker Compose v2。

```bash
git clone <repository-url> movie-pilot-lite
cd movie-pilot-lite
cp .env.example .env
mkdir -p data
docker compose up --build -d
```

打开 `http://localhost:8000`，首次访问时创建管理员密码，然后进入设置页配置第三方连接。

如 Linux 主机上的 bind mount 无写入权限，请让 UID `10001` 可以写入数据目录：

```bash
sudo chown -R 10001:10001 data
```

常用命令：

```bash
docker compose ps
docker compose logs -f movie-pilot-lite
docker compose restart movie-pilot-lite
docker compose down
```

SQLite 数据库保存在宿主机 `./data/movie-pilot-lite.db`。删除容器不会删除该目录。

## M-Team 配置

站点地址填写正常浏览地址，例如：

```text
https://kp.m-team.cc
```

Header 使用 JSON 对象。以下仅为字段格式示例，不要提交真实凭据：

```json
{
  "x-api-key": "your-api-key",
  "Accept": "application/json, text/plain, */*"
}
```

Cookie 使用浏览器请求头格式：

```text
name=value; another=value
```

保存后先点击“测试连接”。搜索调用 M-Team 的 torrent search API；推送前，后端会调用 `genDlToken` 获取短期下载地址，再交给 qBittorrent。搜索结果海报来自 M-Team 返回的 `imageList`，浏览器通过 HTTPS 直接访问，不经过 movie-pilot-lite 代理。

### 每日签到

在设置页启用“每日自动签到”并选择签到时间后，应用每天通过 M-Team `/api/system/hello` 接口签到。签到任务只会在管理员登录、内存配置密钥已解锁后运行；若应用重启导致当天错过计划时间，会在管理员首次登录解锁后补签。设置页会显示最近一次签到的时间、成功或失败状态以及返回消息，关闭开关后仍可保留并调整签到时间。

## 构建 Docker 镜像

Windows PowerShell：

```powershell
.\scripts\build-image.ps1
.\scripts\build-image.ps1 -Tag ghcr.io/example/movie-pilot-lite:0.1.0
.\scripts\build-image.ps1 -Platform linux/amd64,linux/arm64 -Tag ghcr.io/example/movie-pilot-lite:0.1.0 -Push
```

Linux/macOS：

```bash
chmod +x scripts/build-image.sh
./scripts/build-image.sh
./scripts/build-image.sh --tag ghcr.io/example/movie-pilot-lite:0.1.0
./scripts/build-image.sh --platform linux/amd64,linux/arm64 --tag ghcr.io/example/movie-pilot-lite:0.1.0 --push
```

默认使用 `docker buildx build` 并将单平台镜像加载到本地 Docker。使用 `--push` 时，目标 tag 必须是当前账号有权限写入的镜像仓库；多平台构建必须使用 `--push`。

## qBittorrent 配置

填写 qBittorrent Web UI 地址，例如 `http://qbittorrent:8080`。认证支持：

- 用户名和密码；或
- API Key。

Docker Compose 中的地址必须是 movie-pilot-lite 容器可以访问的地址。若 qBittorrent 是另一个 Compose 服务，建议将两个服务加入同一 Docker network，并使用服务名访问。

下载默认值可分别配置四类保存路径：电影、电视剧、音乐和其他。搜索结果会按资源分类预填对应路径，其中“全部”或无法匹配的分类使用“其他”路径；提交单条下载任务时仍可覆盖默认路径。

## 安全说明

- 管理员密码使用 Argon2id 哈希保存。
- M-Team Header/Cookie 与 qBittorrent 密码/API Key 使用 AES-256-GCM 加密。
- 配置回显 API 只返回配置状态和掩码，不返回敏感字段明文；保存后的掩码可直接保留，不需要重复填写凭据。
- HttpOnly、SameSite=Lax Cookie 保存会话，浏览器本地存储不保存 token。
- 容器重启后需要重新登录，以重新解锁内存中的配置密钥。
- 每次新登录都会使旧会话失效。
- 应用不提供删除 qBittorrent 任务或文件的 API。

生产环境建议通过 HTTPS 反向代理发布，不要直接暴露到公网。

## 本地开发

后端要求 Python 3.12 和 uv：

```bash
uv sync --frozen
uv run uvicorn app.main:app --app-dir backend --reload
```

前端要求 Node.js 22 和 pnpm：

```bash
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend dev
```

Vite 会将 `/api` 代理到 `http://127.0.0.1:8000`。

## 验证

```bash
uv run pytest backend/tests -q
pnpm --dir frontend test --run
pnpm --dir frontend build
docker compose config
docker compose up --build -d
```

