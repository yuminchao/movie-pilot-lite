# 设置增强实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 M-Team 配置安全回显，增加每日自动签到、分类型下载路径和搜索结果海报，并保持旧配置兼容。

**Architecture:** 现有加密 `app_config` 继续作为配置存储；设置服务负责敏感值掩码合并和旧配置归一化。M-Team 适配器新增海报解析与保活签到边界，独立签到服务负责日期幂等、失败重试和状态持久化，生命周期调度器只负责按下一执行时间唤醒。React 表单只消费明确 DTO，搜索海报由聚焦组件负责加载失败降级。

**Tech Stack:** Python 3.12、FastAPI、Pydantic、SQLAlchemy、httpx、pytest、pytest-httpx；React、TypeScript、Vite、Vitest、Testing Library、lucide-react。

---

## 文件职责

- `backend/app/services/settings.py`：设置视图、敏感掩码保留、下载路径旧数据归一化。
- `backend/app/api/settings.py`：M-Team、下载路径和签到设置 DTO 与路由。
- `backend/app/integrations/mteam.py`：M-Team 搜索字段解析与 `/api/system/hello` 调用。
- `backend/app/services/checkin.py`：签到配置、状态、日期幂等与 30 分钟单次重试。
- `backend/app/services/checkin_scheduler.py`：应用生命周期内的异步等待、唤醒和停止。
- `backend/app/main.py`：装配签到服务、调度器和 FastAPI lifespan。
- `frontend/src/features/settings/SettingsPage.tsx`：已加载配置表单、签到开关/时间/状态和四类路径。
- `frontend/src/features/search/SearchPage.tsx`：按资源类型选择路径并布置海报。
- `frontend/src/features/search/Poster.tsx`：固定尺寸海报、懒加载和错误占位。
- `frontend/src/lib/types.ts`：前后端设置、签到、路径及 `poster_url` 契约。

### Task 1: M-Team 配置安全回显与保留语义

**Files:**
- Modify: `backend/app/services/settings.py`
- Modify: `backend/app/api/settings.py`
- Modify: `backend/tests/test_settings_api.py`
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/features/settings/SettingsPage.tsx`
- Modify: `frontend/src/App.test.tsx`

- [ ] **Step 1: 写后端失败测试**

在 `backend/tests/test_settings_api.py` 增加以下行为测试：

```python
def test_mteam_settings_echo_public_fields_and_mask_secrets(client) -> None:
    _login(client)
    client.put(
        "/api/settings/mteam",
        json={
            "base_url": "https://m-team.test",
            "headers": {"x-api-key": "secret-key", "Authorization": "secret-auth"},
            "cookie": "tp=secret-cookie",
            "user_agent": "saved-agent",
            "timeout": 23,
        },
    )

    body = client.get("/api/settings/mteam").json()

    assert body["base_url"] == "https://m-team.test"
    assert body["headers"] == {"x-api-key": "••••••••", "Authorization": "••••••••"}
    assert body["cookie"] == "••••••••"
    assert body["user_agent"] == "saved-agent"
    assert body["timeout"] == 23
    assert "secret" not in str(body)


def test_mteam_masked_values_preserve_saved_credentials(client, httpx_mock) -> None:
    _login(client)
    client.put(
        "/api/settings/mteam",
        json={
            "base_url": "https://m-team.test",
            "headers": {"x-api-key": "secret-key"},
            "cookie": "tp=secret-cookie",
            "timeout": 15,
        },
    )
    client.put(
        "/api/settings/mteam",
        json={
            "base_url": "https://m-team.test",
            "headers": {"x-api-key": "••••••••"},
            "cookie": "••••••••",
            "timeout": 30,
        },
    )
    httpx_mock.add_response(
        method="POST",
        url="https://api.m-team.test/api/member/profile",
        json={"data": {"id": "1"}},
    )

    assert client.post("/api/settings/mteam/test").status_code == 200
    request = httpx_mock.get_request()
    assert request.headers["x-api-key"] == "secret-key"
    assert request.headers["Cookie"] == "tp=secret-cookie"
```

- [ ] **Step 2: 运行后端测试并确认正确失败**

Run: `uv run --project . pytest backend/tests/test_settings_api.py -q`

Expected: FAIL，当前响应缺少 `base_url`，且再次保存会把掩码当作真实凭据。

- [ ] **Step 3: 实现后端设置视图和掩码合并**

在 `backend/app/services/settings.py` 定义并使用统一常量与纯合并逻辑：

```python
SECRET_MASK = "••••••••"
DEFAULT_MTEAM = {
    "base_url": "https://kp.m-team.cc",
    "headers": {},
    "cookie": None,
    "user_agent": "movie-pilot-lite/0.1",
    "timeout": 15.0,
}

def _mteam_view(value: dict[str, Any] | None, status: dict[str, Any]) -> dict[str, Any]:
    current = {**DEFAULT_MTEAM, **(value or {})}
    return {
        **status,
        "base_url": current["base_url"],
        "headers": {key: SECRET_MASK for key in current["headers"]},
        "cookie": SECRET_MASK if current.get("cookie") else None,
        "user_agent": current.get("user_agent") or "",
        "timeout": current["timeout"],
    }

def _merge_mteam(existing: dict[str, Any] | None, submitted: dict[str, Any]) -> dict[str, Any]:
    previous = existing or {}
    previous_headers = previous.get("headers", {})
    headers = {}
    for key, value in submitted["headers"].items():
        if value == SECRET_MASK:
            if key not in previous_headers:
                raise ValueError("敏感字段掩码没有可保留的原值")
            headers[key] = previous_headers[key]
        else:
            headers[key] = value
    cookie = submitted.get("cookie")
    if cookie == SECRET_MASK:
        if not previous.get("cookie"):
            raise ValueError("敏感字段掩码没有可保留的原值")
        cookie = previous.get("cookie")
    merged = {**submitted, "headers": headers}
    if cookie:
        merged["cookie"] = cookie
    else:
        merged.pop("cookie", None)
    return merged
```

`get_mteam()` 读取解密配置和状态后返回 `_mteam_view`；`save_mteam()` 先合并再加密保存并返回同一视图。首次提交掩码但没有旧值时抛 `ValueError("敏感字段掩码没有可保留的原值")`，路由转换为 422。路由保存时传递 `payload.model_dump()`，以便空 Cookie 表示显式删除。

- [ ] **Step 4: 运行后端测试并确认通过**

Run: `uv run --project . pytest backend/tests/test_settings_api.py backend/tests/test_config_repository.py -q`

Expected: PASS，响应不包含 `secret-key`、`secret-auth` 或 `secret-cookie`。

- [ ] **Step 5: 写前端失败测试**

在 `frontend/src/App.test.tsx` 增加设置回显用例，模拟 `/api/settings/mteam` 返回完整视图，并断言：

```tsx
expect(await screen.findByDisplayValue('https://m-team.test')).toBeInTheDocument()
expect(screen.getByDisplayValue('saved-agent')).toBeInTheDocument()
expect(screen.getByDisplayValue('23')).toBeInTheDocument()
expect(screen.getByLabelText('Header JSON')).toHaveValue('{\n  "x-api-key": "••••••••"\n}')
expect(screen.getByLabelText('Cookie')).toHaveValue('••••••••')
```

- [ ] **Step 6: 运行前端测试并确认正确失败**

Run: `pnpm --dir frontend test --run src/App.test.tsx`

Expected: FAIL，表单仍显示硬编码默认值。

- [ ] **Step 7: 实现前端 DTO 和异步初始化**

在 `frontend/src/lib/types.ts` 增加：

```typescript
export interface MTeamSettings extends MaskedSettings {
  base_url: string
  headers: Record<string, string>
  cookie: string | null
  user_agent: string
  timeout: number
}
```

`SettingsPage` 将 `mteamStatus` 改为 `MTeamSettings | null`，只在加载完成后挂载 `MTeamForm value={mteamSettings}`。`MTeamForm` 的初始 state 全部来自 `value`，Header 使用 `JSON.stringify(value.headers, null, 2)`，保存后用返回视图重挂载或同步 state，Cookie 原样提交，不再转成 `null`。

- [ ] **Step 8: 运行前后端相关测试和类型检查**

Run: `uv run --project . pytest backend/tests/test_settings_api.py -q`

Run: `pnpm --dir frontend test --run src/App.test.tsx`

Run: `pnpm --dir frontend typecheck`

Expected: 全部 PASS。

- [ ] **Step 9: 提交本任务**

```powershell
git add -- backend/app/services/settings.py backend/app/api/settings.py backend/tests/test_settings_api.py frontend/src/lib/types.ts frontend/src/features/settings/SettingsPage.tsx frontend/src/App.test.tsx
$timestamp = Get-Date -Format 'yyyyMMddHHmmss'
git commit -m "$timestamp fix 修复 M-Team 配置安全回显"
```

### Task 2: 分类型下载路径与旧配置兼容

**Files:**
- Modify: `backend/app/api/settings.py`
- Modify: `backend/app/services/settings.py`
- Modify: `backend/tests/test_settings_api.py`
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/features/settings/SettingsPage.tsx`
- Modify: `frontend/src/features/search/SearchPage.tsx`
- Modify: `frontend/src/App.test.tsx`

- [ ] **Step 1: 写后端失败测试**

增加四路径保存与旧单路径读取测试：

```python
def test_download_defaults_support_type_paths(client) -> None:
    _login(client)
    payload = {
        "category": "downloads",
        "save_paths": {
            "movie": "/downloads/movies",
            "tv": "/downloads/tv",
            "music": "/downloads/music",
            "other": "/downloads/other",
        },
        "start": True,
    }
    assert client.put("/api/settings/downloads", json=payload).json() == payload
    assert client.get("/api/settings/downloads").json() == payload


def test_legacy_download_path_populates_all_types(client) -> None:
    _login(client)
    repository = ConfigRepository(
        client.app.state.database.session_factory,
        client.app.state.secret_vault.cipher,
    )
    repository.set_secret(
        ConfigKey.DOWNLOAD_DEFAULTS,
        {"category": "legacy", "save_path": "/legacy", "start": False},
    )
    assert client.get("/api/settings/downloads").json()["save_paths"] == {
        "movie": "/legacy", "tv": "/legacy", "music": "/legacy", "other": "/legacy"
    }
```

测试直接通过现有 `ConfigRepository` 写入旧结构，不给生产服务增加测试专用接口。

- [ ] **Step 2: 运行后端测试并确认正确失败**

Run: `uv run --project . pytest backend/tests/test_settings_api.py -q`

Expected: FAIL，当前 DTO 只接受 `save_path`。

- [ ] **Step 3: 实现嵌套路径 DTO 和归一化**

在 `backend/app/api/settings.py` 定义：

```python
class DownloadPaths(BaseModel):
    movie: str = Field(min_length=1, max_length=1000)
    tv: str = Field(min_length=1, max_length=1000)
    music: str = Field(min_length=1, max_length=1000)
    other: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_absolute_paths(self) -> "DownloadPaths":
        for value in (self.movie, self.tv, self.music, self.other):
            if not (PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute()):
                raise ValueError("保存路径必须是绝对路径")
        return self
```

`DownloadDefaultsRequest` 使用 `save_paths: DownloadPaths`。`SettingsService.get_download_defaults()` 遇到旧 `save_path` 时构造四个相同值，新配置直接返回；未配置时四项均为 `/downloads`。

- [ ] **Step 4: 运行后端测试并确认通过**

Run: `uv run --project . pytest backend/tests/test_settings_api.py backend/tests/test_search_api.py backend/tests/test_downloads_api.py -q`

Expected: PASS。

- [ ] **Step 5: 写前端失败测试**

在 `frontend/src/App.test.tsx` 将下载默认值 mock 改为 `save_paths`，增加以下断言：

```tsx
expect(await screen.findByDisplayValue('/downloads/movies')).toBeInTheDocument()
expect(screen.getByDisplayValue('/downloads/tv')).toBeInTheDocument()
expect(screen.getByDisplayValue('/downloads/music')).toBeInTheDocument()
expect(screen.getByDisplayValue('/downloads/other')).toBeInTheDocument()
```

搜索用例返回电视剧资源，并断言展开后的“保存路径”为 `/downloads/tv`；再增加 `category: 'all'` 资源断言回退 `/downloads/other`。

- [ ] **Step 6: 运行前端测试并确认正确失败**

Run: `pnpm --dir frontend test --run src/App.test.tsx`

Expected: FAIL，类型和组件仍读取单个 `save_path`。

- [ ] **Step 7: 实现前端四路径表单和类型选择**

在 `frontend/src/lib/types.ts` 改为：

```typescript
export interface DownloadPaths {
  movie: string
  tv: string
  music: string
  other: string
}

export interface DownloadDefaults {
  category: string
  save_paths: DownloadPaths
  start: boolean
}
```

设置页显示“电影路径、电视剧路径、音乐路径、其他路径”四个必填输入。搜索页增加纯函数并用于 `ResultRow` 初始值：

```typescript
function defaultPathFor(category: Category, paths: DownloadPaths) {
  if (category === 'movie' || category === 'tv' || category === 'music') return paths[category]
  return paths.other
}
```

- [ ] **Step 8: 运行相关测试、类型检查并提交**

Run: `uv run --project . pytest backend/tests/test_settings_api.py backend/tests/test_search_api.py backend/tests/test_downloads_api.py -q`

Run: `pnpm --dir frontend test --run src/App.test.tsx`

Run: `pnpm --dir frontend typecheck`

Expected: 全部 PASS。

```powershell
git add -- backend/app/api/settings.py backend/app/services/settings.py backend/tests/test_settings_api.py frontend/src/lib/types.ts frontend/src/features/settings/SettingsPage.tsx frontend/src/features/search/SearchPage.tsx frontend/src/App.test.tsx
$timestamp = Get-Date -Format 'yyyyMMddHHmmss'
git commit -m "$timestamp feat 增加分类型下载路径"
```

### Task 3: 搜索结果海报数据链路与稳定渲染

**Files:**
- Modify: `backend/app/integrations/mteam.py`
- Modify: `backend/app/services/search.py`
- Modify: `backend/tests/test_mteam_client.py`
- Modify: `backend/tests/test_search_api.py`
- Modify: `frontend/src/lib/types.ts`
- Create: `frontend/src/features/search/Poster.tsx`
- Modify: `frontend/src/features/search/SearchPage.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/App.test.tsx`

- [ ] **Step 1: 写后端失败测试**

在 M-Team 搜索响应夹具加入：

```python
"imageList": ["http://unsafe.test/poster.jpg", "https://images.test/poster.jpg"]
```

并断言 `result.poster_url == "https://images.test/poster.jpg"`。增加空列表与非列表用例，断言 `poster_url is None`。在搜索 API 测试断言 `items[0]["poster_url"]` 被投影到响应。

- [ ] **Step 2: 运行后端测试并确认正确失败**

Run: `uv run --project . pytest backend/tests/test_mteam_client.py backend/tests/test_search_api.py -q`

Expected: FAIL，`SearchResult` 没有 `poster_url`。

- [ ] **Step 3: 实现 HTTPS 海报选择和 API 投影**

`SearchResult` 与 `SearchItem` 增加 `poster_url: str | None`。M-Team 适配器使用纯函数：

```python
@staticmethod
def _poster_url(value: object) -> str | None:
    if not isinstance(value, list):
        return None
    return next(
        (item for item in value if isinstance(item, str) and item.startswith("https://")),
        None,
    )
```

`_parse_result()` 传入 `item.get("imageList")`，搜索服务原样投影到 API。

- [ ] **Step 4: 运行后端测试并确认通过**

Run: `uv run --project . pytest backend/tests/test_mteam_client.py backend/tests/test_search_api.py -q`

Expected: PASS。

- [ ] **Step 5: 写前端失败测试**

搜索 mock 项增加 `poster_url: 'https://images.test/poster.jpg'`，断言：

```tsx
const poster = await screen.findByRole('img', { name: '流浪地球 2 海报' })
expect(poster).toHaveAttribute('src', 'https://images.test/poster.jpg')
expect(poster).toHaveAttribute('loading', 'lazy')
```

再以 `fireEvent.error(poster)` 触发失败，断言相同尺寸的 `data-testid="poster-fallback"` 出现。

- [ ] **Step 6: 运行前端测试并确认正确失败**

Run: `pnpm --dir frontend test --run src/App.test.tsx`

Expected: FAIL，页面尚未渲染海报。

- [ ] **Step 7: 实现 Poster 组件和固定布局**

`frontend/src/features/search/Poster.tsx` 实现：

```tsx
import { useEffect, useState } from 'react'
import { ImageOff } from 'lucide-react'

export function Poster({ src, title, size }: { src: string | null; title: string; size: 'thumb' | 'detail' }) {
  const [failed, setFailed] = useState(false)
  useEffect(() => setFailed(false), [src])
  if (!src || failed) {
    return <span className={`poster poster-${size} poster-fallback`} data-testid="poster-fallback"><ImageOff aria-hidden="true" /></span>
  }
  return <img className={`poster poster-${size}`} src={src} alt={`${title} 海报`} loading="lazy" decoding="async" referrerPolicy="no-referrer" onError={() => setFailed(true)} />
}
```

标题列使用 `thumb`；展开区域新增不嵌套卡片的 `download-poster` 区域使用 `detail`。CSS 固定 `48 × 72`、`120 × 180` 和移动端 `44 × 66`，设置 `object-fit: cover`、占位背景与不收缩约束，下载表单使用明确网格列防止图片加载改变布局。

- [ ] **Step 8: 运行测试、类型检查、构建并提交**

Run: `uv run --project . pytest backend/tests/test_mteam_client.py backend/tests/test_search_api.py -q`

Run: `pnpm --dir frontend test --run src/App.test.tsx`

Run: `pnpm --dir frontend typecheck`

Run: `pnpm --dir frontend build`

Expected: 全部 PASS。

```powershell
git add -- backend/app/integrations/mteam.py backend/app/services/search.py backend/tests/test_mteam_client.py backend/tests/test_search_api.py frontend/src/lib/types.ts frontend/src/features/search/Poster.tsx frontend/src/features/search/SearchPage.tsx frontend/src/styles.css frontend/src/App.test.tsx
$timestamp = Get-Date -Format 'yyyyMMddHHmmss'
git commit -m "$timestamp feat 增加搜索结果海报"
```

### Task 4: M-Team 签到服务与设置 API

**Files:**
- Modify: `backend/app/config/repository.py`
- Modify: `backend/app/integrations/mteam.py`
- Create: `backend/app/services/checkin.py`
- Modify: `backend/app/services/settings.py`
- Modify: `backend/app/api/settings.py`
- Modify: `backend/tests/test_mteam_client.py`
- Create: `backend/tests/test_checkin_service.py`
- Modify: `backend/tests/test_settings_api.py`

- [ ] **Step 1: 写 M-Team 签到边界失败测试**

```python
def test_check_in_posts_hello_and_accepts_success_code(mteam_client, httpx_mock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://api.m-team.test/api/system/hello",
        json={"code": "0", "message": "SUCCESS"},
    )
    mteam_client.check_in()
    assert httpx_mock.get_request().headers["x-api-key"] == "secret"


def test_check_in_rejects_business_error(mteam_client, httpx_mock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://api.m-team.test/api/system/hello",
        json={"code": "401", "message": "raw secret detail"},
    )
    with pytest.raises(IntegrationError, match="M-Team 签到失败"):
        mteam_client.check_in()
```

- [ ] **Step 2: 运行边界测试并确认正确失败**

Run: `uv run --project . pytest backend/tests/test_mteam_client.py -q`

Expected: FAIL，`check_in` 尚不存在。

- [ ] **Step 3: 实现脱敏签到调用**

`MTeamClient.check_in()` POST `/api/system/hello`，复用 Header 和 timeout；HTTP 失败、JSON 无效或 `str(code) not in {"0", "200"}` 均抛固定 `IntegrationError("M-Team 签到失败")`，不透传第三方消息。

- [ ] **Step 4: 写签到服务失败测试**

在 `backend/tests/test_checkin_service.py` 使用内存数据库、真实 `ConfigRepository` 和记录调用次数的假客户端，覆盖：

```python
def test_disabled_checkin_never_calls_site(service, fake_client, now) -> None:
    service.save_settings({"enabled": False, "execution_time": "09:00"})
    service.run_due(now.replace(hour=10))
    assert fake_client.calls == 0


def test_success_runs_once_per_local_day(service, fake_client, now) -> None:
    service.save_settings({"enabled": True, "execution_time": "09:00"})
    service.run_due(now.replace(hour=10))
    service.run_due(now.replace(hour=11))
    assert fake_client.calls == 1
    assert service.get_status()["last_success_date"] == now.date().isoformat()


def test_failure_retries_once_after_thirty_minutes(service, fake_client, now) -> None:
    fake_client.fail = True
    service.save_settings({"enabled": True, "execution_time": "09:00"})
    service.run_due(now.replace(hour=10, minute=0))
    service.run_due(now.replace(hour=10, minute=29))
    service.run_due(now.replace(hour=10, minute=30))
    service.run_due(now.replace(hour=11, minute=30))
    assert fake_client.calls == 2
```

- [ ] **Step 5: 运行服务测试并确认正确失败**

Run: `uv run --project . pytest backend/tests/test_checkin_service.py -q`

Expected: FAIL，签到服务尚不存在。

- [ ] **Step 6: 实现签到配置、状态和日期幂等**

在 `ConfigKey` 增加 `MTEAM_CHECKIN = "mteam.checkin"`。`CheckinService` 保存以下单一结构：

```python
{
    "enabled": False,
    "execution_time": "09:00",
    "last_attempt_at": None,
    "last_success_date": None,
    "attempts_on_date": 0,
    "success": None,
    "message": None,
}
```

构造函数接收 `repository_factory`、`client_factory` 和 `ZoneInfo`。`run_due(now)` 将时间转为配置时区，按执行时间、成功日期、当天尝试次数和最后尝试时间决定是否调用；成功写入 `签到成功`，失败只写入固定 `签到失败`。`seconds_until_next(now)` 返回到执行时间、失败重试时间或次日执行时间的非负秒数。

设置 API 增加 `GET/PUT /api/settings/mteam/checkin`，请求为：

```python
class MTeamCheckinRequest(BaseModel):
    enabled: bool
    execution_time: time
```

响应包含 `enabled`、格式化为 `HH:MM` 的 `execution_time`、`last_attempt_at`、`last_success_date`、`success` 和脱敏 `message`。保存 M-Team 连接配置后不改变签到配置。

- [ ] **Step 7: 写并运行签到 API 测试**

增加默认关闭、保存后回显、非法时间 422、响应消息不含第三方原文测试。

Run: `uv run --project . pytest backend/tests/test_mteam_client.py backend/tests/test_checkin_service.py backend/tests/test_settings_api.py -q`

Expected: PASS。

- [ ] **Step 8: 提交本任务**

```powershell
git add -- backend/app/config/repository.py backend/app/integrations/mteam.py backend/app/services/checkin.py backend/app/services/settings.py backend/app/api/settings.py backend/tests/test_mteam_client.py backend/tests/test_checkin_service.py backend/tests/test_settings_api.py
$timestamp = Get-Date -Format 'yyyyMMddHHmmss'
git commit -m "$timestamp feat 增加 M-Team 每日签到服务"
```

### Task 5: 自动签到生命周期调度

**Files:**
- Create: `backend/app/services/checkin_scheduler.py`
- Modify: `backend/app/config/vault.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_checkin_scheduler.py`
- Modify: `backend/tests/test_auth_api.py`

- [ ] **Step 1: 写调度器失败测试**

使用可控假服务和短延迟，不等待真实签到时间：

```python
@pytest.mark.asyncio
async def test_scheduler_runs_due_and_stops_cleanly() -> None:
    service = FakeCheckinService(delay=0)
    scheduler = CheckinScheduler(lambda: service, unlocked=lambda: True)
    await scheduler.start()
    await asyncio.wait_for(service.called.wait(), timeout=1)
    await scheduler.stop()
    assert scheduler.is_running is False


@pytest.mark.asyncio
async def test_scheduler_waits_for_vault_unlock() -> None:
    unlocked = False
    service = FakeCheckinService(delay=0)
    scheduler = CheckinScheduler(lambda: service, unlocked=lambda: unlocked)
    await scheduler.start()
    await asyncio.sleep(0)
    assert service.calls == 0
    unlocked = True
    scheduler.wake()
    await asyncio.wait_for(service.called.wait(), timeout=1)
    await scheduler.stop()
```

- [ ] **Step 2: 运行调度测试并确认正确失败**

Run: `uv run --project . pytest backend/tests/test_checkin_scheduler.py -q`

Expected: FAIL，调度器尚不存在。

- [ ] **Step 3: 实现可停止、可唤醒的调度器**

`CheckinScheduler` 在 `start()` 捕获事件循环并创建一个任务；未解锁时等待 `wake()`，已解锁时通过 `asyncio.to_thread(service.run_due, now)` 执行同步第三方边界，再按 `seconds_until_next()` 等待。等待使用 `asyncio.wait_for(event.wait(), timeout=max(1, delay))`；`wake()` 使用 `loop.call_soon_threadsafe(event.set)`；`stop()` 设置停止标记、唤醒并 await 任务，确保不遗留后台任务。

- [ ] **Step 4: 在保险库解锁和 FastAPI lifespan 中装配**

`SecretVault` 增加注册解锁回调的公开方法，`unlock()` 成功设置 cipher 后逐个调用回调。`create_app()` 构造 `CheckinScheduler`，注册 `scheduler.wake`，并使用：

```python
@asynccontextmanager
async def lifespan(_: FastAPI):
    await scheduler.start()
    try:
        yield
    finally:
        await scheduler.stop()
```

应用状态暴露 `settings_service` 和 `checkin_scheduler` 供路由装配与测试检查。生产部署保持单 Uvicorn worker，避免同一数据库启动多个进程级调度器。

- [ ] **Step 5: 运行调度、认证和完整后端测试**

Run: `uv run --project . pytest backend/tests/test_checkin_scheduler.py backend/tests/test_auth_api.py -q`

Run: `uv run --project . pytest backend/tests -q`

Expected: 全部 PASS，测试结束无 pending task 警告。

- [ ] **Step 6: 提交本任务**

```powershell
git add -- backend/app/services/checkin_scheduler.py backend/app/config/vault.py backend/app/main.py backend/tests/test_checkin_scheduler.py backend/tests/test_auth_api.py
$timestamp = Get-Date -Format 'yyyyMMddHHmmss'
git commit -m "$timestamp feat 启用自动签到调度"
```

### Task 6: 签到设置界面与全量验收

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/features/settings/SettingsPage.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/App.test.tsx`
- Modify: `README.md`

- [ ] **Step 1: 写前端签到设置失败测试**

模拟 `/api/settings/mteam/checkin` 返回：

```typescript
{
  enabled: true,
  execution_time: '09:30',
  last_attempt_at: '2026-08-24T09:30:00+08:00',
  last_success_date: '2026-08-24',
  success: true,
  message: '签到成功',
}
```

断言“每日自动签到”开关已选中、时间输入为 `09:30`、最近状态显示“签到成功”；关闭开关并保存后断言 PUT 载荷为 `{enabled: false, execution_time: '09:30'}`。

- [ ] **Step 2: 运行前端测试并确认正确失败**

Run: `pnpm --dir frontend test --run src/App.test.tsx`

Expected: FAIL，签到控件尚不存在。

- [ ] **Step 3: 实现签到 DTO、开关、时间和状态**

在 `frontend/src/lib/types.ts` 增加：

```typescript
export interface MTeamCheckinSettings {
  enabled: boolean
  execution_time: string
  last_attempt_at: string | null
  last_success_date: string | null
  success: boolean | null
  message: string | null
}
```

`SettingsPage` 初始 `Promise.all` 增加签到 GET。M-Team 区域使用 checkbox 开关和 `type="time"` 输入；关闭时保留时间但不调度。保存按钮调用签到 PUT，状态行显示最近时间、成功/失败和消息。使用现有设置区样式，不新增嵌套卡片。

- [ ] **Step 4: 更新 README**

在功能和使用说明中用中文补充：配置回显仅返回掩码、每日签到在管理员登录解锁后运行、容器重启错过时首次登录补签、四类下载路径及搜索海报来源。

- [ ] **Step 5: 运行前后端完整自动化验证**

Run: `uv run --project . pytest backend/tests -q`

Run: `pnpm --dir frontend test --run`

Run: `pnpm --dir frontend typecheck`

Run: `pnpm --dir frontend build`

Run: `git diff --check`

Expected: 所有测试、类型检查和生产构建 PASS，`git diff --check` 无输出。

- [ ] **Step 6: 浏览器验收**

启动后端：

```powershell
uv run uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

通过 Browser 插件验证 `http://127.0.0.1:8000/settings` 和搜索流程：页面身份正确、非空、无框架错误覆盖层、控制台无相关错误；配置回显、签到开关保存、四类路径回显、搜索海报正常/缺失/失败占位、展开行默认路径与单次覆盖均符合设计。检查桌面 `1440 × 900` 和移动 `390 × 844`，保存截图证据。

- [ ] **Step 7: 提交本任务**

```powershell
git add -- frontend/src/lib/types.ts frontend/src/features/settings/SettingsPage.tsx frontend/src/styles.css frontend/src/App.test.tsx README.md
$timestamp = Get-Date -Format 'yyyyMMddHHmmss'
git commit -m "$timestamp feat 完成设置增强界面"
```

## 计划自检

- 配置回显：Task 1 覆盖公开字段回显、Header/Cookie 掩码、保留、替换和删除。
- 自动签到：Task 4 覆盖第三方边界和日期幂等，Task 5 覆盖解锁、补签、生命周期停止，Task 6 覆盖设置界面。
- 分类型路径：Task 2 覆盖四路径 DTO、旧 `save_path` 兼容、类型匹配和用户单次覆盖。
- 搜索海报：Task 3 覆盖 `imageList` HTTPS 选择、API 契约、固定布局、懒加载和失败占位。
- 安全约束：所有凭据继续加密，响应和错误消息不含明文；海报不经后端代理；重启后不持久化主密钥。
- 类型一致性：统一使用 `MTeamSettings`、`MTeamCheckinSettings`、`DownloadPaths`、`save_paths` 和 `poster_url`。
- 验证范围：包含相关红绿测试、完整测试、类型检查、生产构建、差异检查和桌面/移动浏览器验收。
