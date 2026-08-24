import { FormEvent, useEffect, useState } from 'react'
import { CheckCircle2, Database, FolderDown, PlugZap, Server } from 'lucide-react'

import { api, ApiError } from '../../lib/api'
import type { DownloadDefaults, MaskedSettings, MTeamSettings } from '../../lib/types'

export function SettingsPage() {
  const [mteamStatus, setMteamStatus] = useState<MTeamSettings | null>(null)
  const [qbStatus, setQbStatus] = useState<MaskedSettings | null>(null)
  const [downloadDefaults, setDownloadDefaults] = useState<DownloadDefaults | null>(null)

  useEffect(() => {
    Promise.all([
      api.get<MTeamSettings>('/api/settings/mteam'),
      api.get<MaskedSettings>('/api/settings/qbittorrent'),
      api.get<DownloadDefaults>('/api/settings/downloads'),
    ]).then(([mteam, qb, defaults]) => {
      setMteamStatus(mteam)
      setQbStatus(qb)
      setDownloadDefaults(defaults)
    })
  }, [])

  return (
    <main className="page settings-page">
      <div className="page-heading"><div><h1>连接设置</h1><p>配置 M-Team 认证信息和 qBittorrent Web API</p></div></div>
      <div className="settings-grid">
        {mteamStatus ? <MTeamForm value={mteamStatus} onSaved={setMteamStatus} /> : null}
        <QbittorrentForm status={qbStatus} onSaved={setQbStatus} />
        {downloadDefaults ? (
          <DownloadDefaultsForm value={downloadDefaults} onSaved={setDownloadDefaults} />
        ) : null}
      </div>
      <div className="security-note"><Database size={18} /><span>敏感字段使用管理员密码派生密钥加密后保存到 SQLite，页面不会读回明文。</span></div>
    </main>
  )
}

function DownloadDefaultsForm({ value, onSaved }: { value: DownloadDefaults; onSaved: (value: DownloadDefaults) => void }) {
  const [category, setCategory] = useState(value.category)
  const [savePath, setSavePath] = useState(value.save_path)
  const [start, setStart] = useState(value.start)
  const [message, setMessage] = useState('')

  async function save(event: FormEvent) {
    event.preventDefault()
    try {
      const result = await api.put<DownloadDefaults>('/api/settings/downloads', {
        category,
        save_path: savePath,
        start,
      })
      onSaved(result)
      setMessage('下载默认值已保存')
    } catch (reason) {
      setMessage(reason instanceof ApiError ? reason.message : '保存失败')
    }
  }

  return (
    <section className="settings-section defaults-section">
      <div className="section-title"><span className="section-icon defaults"><FolderDown size={20} /></span><div><h2>下载默认值</h2><p>搜索结果展开时预填，单条任务仍可覆盖</p></div></div>
      <form className="defaults-form" onSubmit={save}>
        <label>默认分类<input value={category} onChange={(event) => setCategory(event.target.value)} /></label>
        <label>默认保存路径<input value={savePath} onChange={(event) => setSavePath(event.target.value)} /></label>
        <label>默认启动方式<select value={start ? 'start' : 'paused'} onChange={(event) => setStart(event.target.value === 'start')}><option value="start">立即开始</option><option value="paused">暂停添加</option></select></label>
        <button className="primary-button" type="submit">保存默认值</button>
        {message ? <p className="settings-message" role="status">{message}</p> : null}
      </form>
    </section>
  )
}

function StatusLine({ status }: { status: MaskedSettings | null }) {
  return (
    <div className={`connection-status ${status?.configured ? 'configured' : ''}`}>
      <span>{status?.configured ? <CheckCircle2 size={16} /> : <span className="status-dot" />}</span>
      <strong>{status?.configured ? '已配置' : '尚未配置'}</strong>
      {status?.updated_at ? <small>更新于 {new Date(status.updated_at).toLocaleString('zh-CN')}</small> : null}
    </div>
  )
}

function MTeamForm({ value, onSaved }: { value: MTeamSettings; onSaved: (value: MTeamSettings) => void }) {
  const [baseUrl, setBaseUrl] = useState(value.base_url)
  const [headers, setHeaders] = useState(JSON.stringify(value.headers, null, 2))
  const [cookie, setCookie] = useState(value.cookie ?? '')
  const [userAgent, setUserAgent] = useState(value.user_agent ?? '')
  const [timeout, setTimeoutValue] = useState(value.timeout)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  async function save(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setMessage('')
    try {
      const parsedHeaders = JSON.parse(headers) as Record<string, string>
      const result = await api.put<MTeamSettings>('/api/settings/mteam', { base_url: baseUrl, headers: parsedHeaders, cookie: cookie || null, user_agent: userAgent || null, timeout })
      setBaseUrl(result.base_url)
      setHeaders(JSON.stringify(result.headers, null, 2))
      setCookie(result.cookie ?? '')
      setUserAgent(result.user_agent ?? '')
      setTimeoutValue(result.timeout)
      onSaved(result)
      setMessage('M-Team 配置已加密保存')
    } catch (reason) {
      setMessage(reason instanceof SyntaxError ? 'Header JSON 格式无效' : reason instanceof ApiError ? reason.message : '保存失败')
    } finally {
      setBusy(false)
    }
  }

  async function testConnection() {
    setMessage('正在测试 M-Team 连接...')
    try {
      const result = await api.post<{ message: string }>('/api/settings/mteam/test')
      setMessage(result.message)
    } catch (reason) {
      setMessage(reason instanceof ApiError ? reason.message : '连接测试失败')
    }
  }

  return (
    <section className="settings-section">
      <div className="section-title"><span className="section-icon"><Server size={20} /></span><div><h2>M-Team</h2><p>站点搜索和临时下载地址认证</p></div><StatusLine status={value} /></div>
      <form onSubmit={save}>
        <div className="field-row"><label>站点地址<input type="url" value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} required /></label><label>请求超时（秒）<input type="number" min="1" max="60" value={timeout} onChange={(event) => setTimeoutValue(Number(event.target.value))} /></label></div>
        <label>Header JSON<textarea rows={5} value={headers} onChange={(event) => setHeaders(event.target.value)} spellCheck={false} /></label>
        <label>Cookie<textarea rows={3} value={cookie} onChange={(event) => setCookie(event.target.value)} placeholder={value.configured ? value.masked ?? '' : 'tp=...; uid=...'} spellCheck={false} /></label>
        <label>User-Agent<input value={userAgent} onChange={(event) => setUserAgent(event.target.value)} /></label>
        {message ? <p className="settings-message" role="status">{message}</p> : null}
        <div className="form-actions"><button className="secondary-button" type="button" onClick={testConnection}><PlugZap size={16} />测试连接</button><button className="primary-button" type="submit" disabled={busy}>{busy ? '保存中...' : '保存配置'}</button></div>
      </form>
    </section>
  )
}

function QbittorrentForm({ status, onSaved }: { status: MaskedSettings | null; onSaved: (status: MaskedSettings) => void }) {
  const [baseUrl, setBaseUrl] = useState('http://qbittorrent:8080')
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  async function save(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setMessage('')
    try {
      const result = await api.put<MaskedSettings>('/api/settings/qbittorrent', { base_url: baseUrl, username: username || null, password: password || null, api_key: apiKey || null })
      onSaved(result)
      setMessage('qBittorrent 配置已加密保存')
    } catch (reason) {
      setMessage(reason instanceof ApiError ? reason.message : '保存失败')
    } finally {
      setBusy(false)
    }
  }

  async function testConnection() {
    setMessage('正在测试 qBittorrent 连接...')
    try {
      const result = await api.post<{ message: string }>('/api/settings/qbittorrent/test')
      setMessage(result.message)
    } catch (reason) {
      setMessage(reason instanceof ApiError ? reason.message : '连接测试失败')
    }
  }

  return (
    <section className="settings-section">
      <div className="section-title"><span className="section-icon qb"><PlugZap size={20} /></span><div><h2>qBittorrent</h2><p>下载任务提交与状态读取</p></div><StatusLine status={status} /></div>
      <form onSubmit={save}>
        <label>Web UI 地址<input type="url" value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} required /></label>
        <div className="field-row"><label>用户名<input value={username} onChange={(event) => setUsername(event.target.value)} /></label><label>密码<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder={status?.configured ? status.masked ?? '' : ''} /></label></div>
        <label>API Key（与用户名密码二选一）<input type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder={status?.configured ? status.masked ?? '' : ''} /></label>
        {message ? <p className="settings-message" role="status">{message}</p> : null}
        <div className="form-actions"><button className="secondary-button" type="button" onClick={testConnection}><PlugZap size={16} />测试连接</button><button className="primary-button" type="submit" disabled={busy}>{busy ? '保存中...' : '保存配置'}</button></div>
      </form>
    </section>
  )
}
