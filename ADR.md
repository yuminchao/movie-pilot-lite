# ADR 记录（Architecture Decision Records）

本文件记录 movie-pilot-lite 项目的关键架构决策。每次新决策按顺序追加，格式见 ADR-001。

---

## ADR-001：存储从 SQLite 迁移到 MySQL

- **日期**：2026-08-30
- **状态**：已接受（Accepted）
- **背景**：项目最初使用 SQLite（`sqlite:///./data/movie-pilot-lite.db`）作为唯一存储。用户要求改为 MySQL，已在宿主机 `/data/mysql` 通过 Docker 部署 MySQL 8.4（容器名 `mysql`，端口 3306）。
- **决策**：
  1. 新增依赖 `pymysql`（纯 Python 驱动；MySQL 8 的 `caching_sha2_password` 认证依赖已有的 `cryptography` 包）。
  2. `backend/app/db/session.py`：
     - 非 SQLite 连接启用 `pool_pre_ping=True` 与 `pool_recycle=3600`，避免连接被服务端/网络中断。
     - 新增 `ensure_database()`：MySQL 下按 utf8mb4 自动 `CREATE DATABASE IF NOT EXISTS`，部署时无需手动建库；SQLite 下为空操作。
  3. `backend/alembic/env.py`：在线迁移前调用 `ensure_database()`，保证 `alembic upgrade head` 在全新环境可直接执行。
  4. 数据库地址统一由环境变量 `DATABASE_URL` 提供；`docker-compose.yml` 改为必填（`${DATABASE_URL:?}`）并通过 `extra_hosts` 支持 `host.docker.internal` 访问宿主机 MySQL；`.env.example` 与 `backend/alembic.ini` 默认值同步更新为 MySQL。
  5. 测试继续使用 SQLite（`tmp_path`），不依赖外部 MySQL，保持 CI 快速稳定。
- **后果**：
  - 时间字段：MySQL `DATETIME` 不带时区，返回 naive datetime；代码中已有的 `_as_utc` 帮助函数已按 UTC 解释，无需修改。
  - 迁移脚本 `0001_initial` 未改动：布尔列映射为 `TINYINT(1)`，主键为 `AUTO_INCREMENT`，`app_config.key` 列名由 SQLAlchemy 自动加反引号转义，均兼容 MySQL。
  - 首次初始化 root 密码与 `.env` 不一致（MySQL 官方镜像只在数据目录首次初始化时应用密码）；已通过 `--skip-grant-tables` 重置为 `.env` 中的密码 并重建应用数据库。
- **验证**：`pytest`（SQLite 回归）通过；`alembic upgrade head` 在真实 MySQL 8.4 上成功建表；应用以 MySQL 为存储启动并通过 `/api/health`。

---

## ADR-002：全站统一挂载 /mpl 前缀并经 nginx 反向代理发布

- **日期**：2026-08-30
- **状态**：已接受（Accepted）
- **背景**：应用需要与宿主机其他服务（如 dsh 等）共存于同一入口。用户要求所有页面与接口统一加 `/mpl` 前缀，并通过 `/data/nginx` 的 nginx（容器 `nginx-custom`，host 网络，`https://192.168.3.36:8080`）对外发布。
- **决策**：
  1. **应用层完整实现前缀**（而非 nginx 层重写），保证直连 `:8000` 与经代理行为一致：
     - 后端 `main.py`：四个 API router 统一 `prefix="/mpl"`；健康检查改为 `/mpl/api/health`；静态资源挂载 `/mpl/assets`；SPA fallback 路由改为 `/mpl/{path:path}`；凭据脱敏端点集合同步更新。
     - 前端：`api.ts` 内部统一拼接 `API_BASE='/mpl'`（各调用点与前端测试无需改动）；`BrowserRouter basename="/mpl"`；Vite `base='/mpl/'` 与 dev proxy 更新。
     - `docker/healthcheck.py` 更新为 `/mpl/api/health`；后端测试路径断言批量更新。
  2. **nginx 简单透传**：`location /mpl/ { proxy_pass http://127.0.0.1:8000; ... }`（`proxy_pass` 不带 URI，保留 `/mpl` 前缀原样转发），并保留标准代理头。
  3. 无前缀路径（`/`、`/api/*`）统一返回 404，避免绕过前缀直连。
- **后果**：
  - 访问入口变为 `https://192.168.3.36:8080/mpl/`（页面）与 `/mpl/api/*`（接口）；直连 `http://localhost:8000/mpl/` 同样可用。
  - 前端测试需将初始 URL 设为 `/mpl/` 以匹配 basename。
  - nginx.conf 修改前已备份（`nginx.conf.bak.*`）。
- **验证**：后端 pytest 131 通过；前端 vitest 24 通过；镜像重建后经 nginx 访问 `/mpl/api/health`、`/mpl/`、`/mpl/assets/*`、SPA 路由 `/mpl/search` 均 200；无前缀路径 404。

---

## ADR-003：主导航从顶部改为左侧边栏

- **日期**：2026-08-30
- **状态**：已接受（Accepted）
- **背景**：用户希望主界面导航从顶部横排菜单改为左侧纵向边栏，便于扩展更多菜单项并贴合常见管理后台布局。
- **决策**：
  1. `App.tsx`：`<header class="topbar">` 改为 `<aside class="sidebar">`——品牌区在上、导航竖排（搜索/下载任务/设置）、退出按钮沉底（`margin-top: auto`）；内容包进 `<main class="app-main">`。
  2. `styles.css`：`app-shell` 改为横向 flex；侧栏固定宽 200px、`position: sticky` 撑满视口高度，深色导航底色沿用 `--nav`；激活项以圆角背景 + 图标高亮标识（替代原下划线）；响应式 ≤680px 时侧栏收窄为 58px 图标栏（隐藏文字保留图标）。
  3. 导航项文字包裹 `<span>`，便于窄屏按需隐藏；前端测试无布局断言，无需改动。
- **后果**：主内容区左侧固定深色导航；移动端退化为紧凑图标栏；`.page` 内容宽度与既有响应式断点保持不变。
- **验证**：前端 vitest 24 通过；`pnpm build` 成功；镜像重建部署后经 nginx 访问正常，容器 healthy。

---

## ADR-004：用 Prowlarr + Radarr + Sonarr 替换自研 movie-pilot-lite

- **日期**：2026-10-21
- **状态**：已接受（Accepted）
- **背景**：自研的 movie-pilot-lite（FastAPI + React + MySQL + nginx /mpl）功能有限，用户决定改用成熟的 *arr 组合（Prowlarr + Radarr + Sonarr）接管 M-Team 搜索、自动下载、媒体库整理。
- **决策**：
  1. 停止并移除 movie-pilot-lite 容器；**保留** MySQL `movie_pilot_lite` 库与 `data/movie-pilot-lite.db`（旧 SQLite）数据，不做删除。
  2. 在 `arr/` 目录用 docker compose 部署三件套（linuxserver 镜像）：Prowlarr `9696`、Radarr `7878`、Sonarr `8989`；`PUID/PGID=0`、`TZ=Asia/Shanghai`。
  3. 存储布局：`arr/storage/media/movies`、`arr/storage/media/tv`、`arr/storage/downloads`，Radarr/Sonarr 统一挂载 `./storage:/data`，保证下载与媒体库在同一挂载点（硬链接可用）。
  4. qBittorrent 沿用用户已有的外部实例（本机无 qB 容器），在 Radarr/Sonarr 的 Download Clients 中填写地址与账号。
  5. nginx 的 `/mpl` 反代块已注释（避免 502），*arr 先以直连端口方式访问；后续如需反代再配置 URL Base。
- **后果**：
  - 访问入口：`http://192.168.3.36:7878`（Radarr）、`:8989`（Sonarr）、`:9696`（Prowlarr）；8000 端口已释放。
  - 后续配置：Prowlarr 添加 `M-Team - TP` 索引器（x-api-key）→ Radarr/Sonarr 添加 Prowlarr（API Key 同步索引器）→ 配置 qBittorrent 下载客户端 → 设置媒体根目录（`/data/media/movies`、`/data/media/tv`）。
  - 局域网内 *arr 默认免登录（`Disabled for Local Addresses`）；经 nginx/公网暴露时需开启 Forms 认证。
  - 2026-10-21 补充：Prowlarr 经 ymc-pub 外层 nginx（`/data/nginx/nginx.conf`）以 **9085 端口 https 终结** 暴露，
    配置片段与幂等脚本位于 `ymc-pub/scripts/prowlarr-location.txt`、`apply-nginx-prowlarr.sh`。
    注意反代**不传** `X-Real-IP`/`X-Forwarded-For`：Prowlarr 的本地免认证以请求源 IP 判定，传客户端 IP 会跳登录页。
    Prowlarr `config.xml` 同步调整 `AllowedHosts=ymc.pub,192.168.3.36,localhost,127.0.0.1`。
  - 2026-10-21 补充：在 ymc-pub 门户菜单（`ymc_pub.portal_menu`）新增 Prowlarr 入口
    （name=Prowlarr, url=https://ymc.pub:9085/, sort_order=21），Prowlarr 无 X-Frame-Options，可正常 iframe 嵌入。
- **验证**：三容器启动成功且 HTTP 200；8000 端口释放；mysql/nginx 保持运行。

---

## ADR-005：停用 Prowlarr，恢复 movie-pilot-lite

- **日期**：2026-10-29
- **状态**：已接受（Accepted）；部分取代 ADR-004
- **背景**：用户反馈 Prowlarr 不好用，要求停掉并恢复原 movie-pilot-lite 服务，并在 ymc-pub 门户加入口。
- **决策**：
  1. `arr/` 中仅 `docker compose stop prowlarr`（容器与 `arr/config/prowlarr` 保留，可随时 `start`）；同日按用户要求 Radarr/Sonarr 也一并 `stop`（同样保留容器与配置）。
  2. 用现有镜像 `movie-pilot-lite-movie-pilot-lite`（`docker compose up -d --no-build`）恢复容器，端口 8000，数据仍为 MySQL `movie_pilot_lite` 库。
  3. `/data/nginx/nginx.conf` 取消注释 `location /mpl/` 反代块（改前已备份 `nginx.conf.bak.*`）；9085 的 Prowlarr server 块保留未删。
  4. `ymc_pub.portal_menu`：Prowlarr（id=13）置 `enabled=0`；新增 `MoviePilot Lite`（id=15，url=https://ymc.pub:8080/mpl/，sort_order=21）。
- **后果**：入口 `https://ymc.pub:8080/mpl/`；9085 端口因 Prowlarr 停止会返回 502（门户已隐藏该入口）。
- **验证**：容器 healthy；直连与经 nginx 访问 `/mpl/api/health` 均 200；`/mpl/` 页面 200，无 X-Frame-Options，可在门户 iframe 嵌入。

---

## ADR-006：搜索结果展示音轨语言并支持按语言筛选

- **日期**：2026-10-29
- **状态**：已接受（Accepted）
- **背景**：用户希望搜索结果能看出国语、英语等语言。M-Team 搜索接口没有结构化语言字段，只有 `labelsNew`（`中配`/`中字`/`4k` 等）以及标题、副标题里的发布惯用写法。
- **决策**：
  1. 新增 `backend/app/integrations/release_languages.py`，启发式识别音轨语言：`中配` 标签 → 国语；副标题中的「国语/粤语/英语…」「国配/台配」、紧凑写法「国粤双语」「法英三语」「中英音轨」；标题中的 `[HIN+ENG+KOR]` 代码列表与 Mandarin/Cantonese。紧跟「字幕/字」的、含「简/繁」的、不带「音轨」的「中英双语」均视为字幕说明，不计入。另从 `2Audio`/`4Audios` 读出音轨数。
  2. `SearchResult`/`SearchItem` 新增 `audio_languages`、`audio_tracks` 字段返回前端。
  3. 前端结果行新增标签行：语言（蓝色）、「N 音轨」、站点标签（`中配` 与语言重复，不再单独展示）；工具栏新增「语言」下拉，选项取当前页出现过的语言，前端本地筛选。
  4. 顺带修复：`labelsNew` 为空时回退旧 `labels` 字段，其值多为数字位掩码（如 `"0"`），现过滤纯数字项。
- **后果**：没写语言的资源识别不到（如欧美片默认原声英语但副标题不写），这类结果不带语言标签，选了语言筛选后会被隐藏。实测「无间道」100 条中 51 条识别出语言。
- **验证**：后端 pytest 146 通过（新增 `test_release_languages.py`）；前端 vitest 25 通过、`tsc -b` 通过；镜像重建部署后容器 healthy。

---

## ADR-007：搜索覆盖 M-Team 全部一级分类；并入视频下载页

- **日期**：2026-10-29
- **状态**：已接受（Accepted）
- **背景**：用户要求把 M-Team 上的分类都纳入搜索，并把 ymc-pub 门户里做的「视频下载」（video-grab，见 ymc-pub ADR-021）合并到 movie-pilot-lite。
- **决策**：
  1. **分类**：按 M-Team `/api/torrent/categoryList` 的一级分类建表 `_CATEGORY_IDS`：电影、剧集/综艺、纪录、动漫、音乐、游戏、其他、成人（AV 有码/无码、IV、H-ACG）。成人区必须带 `mode=adult` 搜索，其余为 `normal`；因此「全部」不含成人区。结果分类按子分类 id 反查，未知 id 归「其他」。原先电影/剧集里混入的纪录（404）、动画（405）拆为独立分类。
  2. **视频下载**：新增 `/mpl/api/video/**`（需登录）转发到 video-grab（`X-Grab-Token`），文件接口流式转发并透传 `Range`，支持在线播放与拖动。前端侧栏新增「视频下载」页，功能与门户版一致：批量提交网址、文件名、抓取模式、设置面板、播放/下载/重试/取消/删除（可连文件）、查看日志；有进行中任务时 3 秒刷新，否则 15 秒。
  3. **部署**：video-grab 仍由 ymc-pub 的 compose 管理，movie-pilot-lite 以外部网络 `ymc-pub_default` 接入，经 `http://video-grab:8095` 访问；令牌 `VIDEO_GRAB_TOKEN` 写入本项目 `.env`（与 ymc-pub/.env 相同）。门户里原有的视频下载页暂时保留。
- **后果**：movie-pilot-lite 依赖 `ymc-pub_default` 网络存在；若 ymc-pub 整体 `docker compose down` 删掉了该网络，本项目重建容器前需先把 ymc-pub 拉起来。两处页面共用同一个 video-grab，任务列表一致。
- **验证**：后端 pytest 159 通过（新增 `test_video_api.py`、分类映射用例）；前端 vitest 26 通过、`tsc -b` 通过；部署后容器 healthy，容器内访问 video-grab 设置与任务接口正常；实测纪录/动漫/游戏/其他/成人分类搜索各返回 100 条且分类归属正确。

---

## ADR 模板（后续决策请复制此结构追加）

- **日期**：YYYY-MM-DD
- **状态**：提议（Proposed）/ 已接受（Accepted）/ 已废弃（Deprecated）
- **背景**：……
- **决策**：……
- **后果**：……
- **验证**：……
