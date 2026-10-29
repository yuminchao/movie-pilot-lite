import { FormEvent, useCallback, useEffect, useRef, useState } from 'react'
import { AlertTriangle, CheckCircle2, CircleSlash, CloudDownload, Download, Play, RotateCcw, Settings, Square, Trash2, Video } from 'lucide-react'

import { api, ApiError, apiUrl } from '../../lib/api'
import type { VideoGrabMode, VideoGrabSettings, VideoTask, VideoTaskStatus } from '../../lib/types'

const statusLabels: Record<VideoTaskStatus, string> = {
  queued: '排队中',
  running: '下载中',
  done: '完成',
  failed: '失败',
  canceled: '已取消',
}

const modeOptions: Array<{ value: VideoGrabMode; label: string }> = [
  { value: 'auto', label: '自动（先找地址，找不到就边播边录）' },
  { value: 'url', label: '只按地址下载' },
  { value: 'mse', label: '强制边播边录' },
]

function errorMessage(reason: unknown, fallback: string) {
  return reason instanceof ApiError ? reason.message : fallback
}

/** 视频下载页：提交网页地址，后台用无头浏览器抓视频；列表里可播放、下载、重试。 */
export function VideoPage() {
  const [tasks, setTasks] = useState<VideoTask[] | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [urls, setUrls] = useState('')
  const [name, setName] = useState('')
  const [mode, setMode] = useState<VideoGrabMode | ''>('')
  const [submitting, setSubmitting] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const timer = useRef<number | undefined>(undefined)

  const load = useCallback(async () => {
    try {
      const list = await api.get<VideoTask[]>('/api/video/tasks')
      setTasks(list)
      setError('')
      return list
    } catch (reason) {
      setError(errorMessage(reason, '加载视频任务失败'))
      return null
    }
  }, [])

  // 有进行中的任务时 3 秒刷新一次，否则 15 秒
  const schedule = useCallback(async () => {
    window.clearTimeout(timer.current)
    const list = await load()
    const busy = (list ?? []).some((task) => task.status === 'queued' || task.status === 'running')
    timer.current = window.setTimeout(() => void schedule(), busy ? 3000 : 15000)
  }, [load])

  useEffect(() => {
    void schedule()
    return () => window.clearTimeout(timer.current)
  }, [schedule])

  const urlList = urls.split(/\s+/).map((value) => value.trim()).filter(Boolean)

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!urlList.length) return
    setSubmitting(true)
    setNotice('')
    try {
      const created = await api.post<VideoTask[]>('/api/video/tasks', {
        urls: urlList,
        name: urlList.length === 1 ? name.trim() || undefined : undefined,
        mode: mode || undefined,
      })
      setNotice(`已加入 ${created.length} 个任务`)
      setUrls('')
      setName('')
      await schedule()
    } catch (reason) {
      setError(errorMessage(reason, '提交失败'))
    } finally {
      setSubmitting(false)
    }
  }

  async function act(action: () => Promise<unknown>, ok: string) {
    setNotice('')
    try {
      await action()
      setNotice(ok)
      await schedule()
    } catch (reason) {
      setError(errorMessage(reason, '操作失败'))
    }
  }

  return (
    <main className="page video-page">
      <div className="page-heading">
        <div><h1>视频下载</h1><p>粘贴网页地址，后台打开网页、自动播放并把视频保存到服务器</p></div>
        <button className="secondary-button" type="button" onClick={() => setSettingsOpen(!settingsOpen)} aria-expanded={settingsOpen}><Settings size={16} />设置</button>
      </div>
      {settingsOpen ? <VideoSettingsPanel onClose={() => setSettingsOpen(false)} onSaved={() => setNotice('设置已保存')} /> : null}
      <form className="video-form settings-section" onSubmit={submit}>
        <textarea
          aria-label="网页地址"
          rows={3}
          value={urls}
          onChange={(event) => setUrls(event.target.value)}
          placeholder="粘贴网页地址，一行一个"
        />
        <div className="video-form-row">
          <input aria-label="文件名" value={name} onChange={(event) => setName(event.target.value)} placeholder="文件名（可选，默认用网页标题）" disabled={urlList.length > 1} />
          <select aria-label="抓取模式" value={mode} onChange={(event) => setMode(event.target.value as VideoGrabMode | '')}>
            <option value="">抓取模式：按设置</option>
            {modeOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
          <button className="primary-button" type="submit" disabled={submitting || !urlList.length}>
            <CloudDownload size={16} />{submitting ? '提交中...' : `开始下载${urlList.length > 1 ? `（${urlList.length} 个）` : ''}`}
          </button>
        </div>
      </form>
      {error ? <div className="alert error" role="alert">{error}</div> : null}
      {notice ? <div className="alert success" role="status">{notice}</div> : null}
      <section className="task-list">
        {(tasks ?? []).map((task) => (
          <VideoTaskRow
            key={task.id}
            task={task}
            onRetry={() => act(() => api.post(`/api/video/tasks/${task.id}/retry`), '已重新排队')}
            onCancel={() => act(() => api.post(`/api/video/tasks/${task.id}/cancel`), '已取消')}
            onDelete={(deleteFile) => act(() => api.delete(`/api/video/tasks/${task.id}${deleteFile ? '?deleteFile=1' : ''}`), '已删除')}
          />
        ))}
        {tasks && tasks.length === 0 ? <div className="empty-state"><Video size={28} /><strong>还没有视频任务</strong><span>粘贴网页地址开始下载</span></div> : null}
        {!tasks && !error ? <div className="empty-state"><Video size={28} /><strong>正在加载...</strong></div> : null}
      </section>
    </main>
  )
}

function VideoTaskRow({ task, onRetry, onCancel, onDelete }: { task: VideoTask; onRetry: () => void; onCancel: () => void; onDelete: (deleteFile: boolean) => void }) {
  const [playing, setPlaying] = useState(false)
  const [showLog, setShowLog] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [deleteFile, setDeleteFile] = useState(false)
  const Icon = task.status === 'done' ? CheckCircle2 : task.status === 'failed' ? AlertTriangle : task.status === 'canceled' ? CircleSlash : Download
  const finished = task.status === 'done' || task.status === 'failed' || task.status === 'canceled'
  const title = task.file ? task.file.split('/').pop() : task.name || task.title || '（未取到标题）'

  return (
    <article className="task-row video-task">
      <span className={`task-icon ${task.status}`}><Icon size={18} /></span>
      <div className="task-main">
        <div className="task-title"><strong title={task.file || task.title}>{title}</strong><span>{statusLabels[task.status]}</span></div>
        <a className="video-url" href={task.url} target="_blank" rel="noreferrer">{task.url}</a>
        <p className={`video-progress ${task.status === 'failed' ? 'failed' : ''}`}>{task.status === 'failed' ? task.error || task.progress : task.progress}</p>
        <div className="task-meta">
          <span>{formatTime(task.createdAt)}{task.size ? ` · ${formatSize(task.size)}` : ''}</span>
          <span className="video-actions">
            {task.status === 'done' ? <>
              <button className="icon-button" type="button" title="播放" onClick={() => setPlaying(!playing)}><Play size={15} /></button>
              <a className="icon-button" title="下载到本机" href={apiUrl(`/api/video/tasks/${task.id}/file`)}><Download size={15} /></a>
            </> : null}
            {finished ? <button className="icon-button" type="button" title="重新下载" onClick={onRetry}><RotateCcw size={15} /></button> : null}
            {!finished ? <button className="icon-button" type="button" title="取消" onClick={onCancel}><Square size={15} /></button> : null}
            {task.log.length ? <button className="secondary-button" type="button" onClick={() => setShowLog(!showLog)}>日志</button> : null}
            <button className="icon-button danger" type="button" title="删除" onClick={() => { setDeleteFile(false); setConfirming(!confirming) }}><Trash2 size={15} /></button>
          </span>
        </div>
        {confirming ? (
          <div className="video-confirm">
            <span>删除这条任务？</span>
            {task.file ? <label><input type="checkbox" checked={deleteFile} onChange={(event) => setDeleteFile(event.target.checked)} />同时删除视频文件</label> : null}
            <button className="primary-button" type="button" onClick={() => { setConfirming(false); onDelete(deleteFile) }}>确认删除</button>
            <button className="secondary-button" type="button" onClick={() => setConfirming(false)}>取消</button>
          </div>
        ) : null}
        {playing ? <video className="video-player" src={apiUrl(`/api/video/tasks/${task.id}/file?inline=true`)} controls autoPlay /> : null}
        {showLog ? <pre className="video-log">{task.log.join('\n')}</pre> : null}
      </div>
    </article>
  )
}

/** 设置面板：保存目录、代理、并发、超时、抓取模式、Cookie。 */
function VideoSettingsPanel({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [value, setValue] = useState<VideoGrabSettings | null>(null)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.get<VideoGrabSettings>('/api/video/settings').then(setValue).catch((reason) => setError(errorMessage(reason, '读取设置失败')))
  }, [])

  function update<K extends keyof VideoGrabSettings>(key: K, next: VideoGrabSettings[K]) {
    setValue((current) => (current ? { ...current, [key]: next } : current))
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    if (!value) return
    setSaving(true)
    setError('')
    try {
      const body: Partial<VideoGrabSettings> = { ...value }
      delete body.root
      await api.put('/api/video/settings', body)
      onSaved()
      onClose()
    } catch (reason) {
      setError(errorMessage(reason, '保存设置失败'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="settings-section video-settings">
      {error ? <div className="alert error" role="alert">{error}</div> : null}
      {value ? (
        <form onSubmit={save}>
          <label>保存目录<input required value={value.saveDir} onChange={(event) => update('saveDir', event.target.value)} /><small>相对于 {value.root || '保存根目录'}，宿主机上是 /data/downloads 下的同名目录</small></label>
          <label>代理<input value={value.proxy} placeholder="http://host:port" onChange={(event) => update('proxy', event.target.value)} /><small>访问国外网站时填写，如 http://192.168.3.50:7890；留空直连</small></label>
          <div className="video-settings-grid">
            <label>同时下载数<input type="number" min={1} max={4} required value={value.concurrency} onChange={(event) => update('concurrency', Number(event.target.value))} /></label>
            <label>失败自动重试次数<input type="number" min={0} max={3} required value={value.retries} onChange={(event) => update('retries', Number(event.target.value))} /></label>
            <label>嗅探等待（秒）<input type="number" min={5} max={120} required value={value.wait} onChange={(event) => update('wait', Number(event.target.value))} /></label>
            <label>录制上限（秒）<input type="number" min={60} max={14400} step={60} required value={value.maxDuration} onChange={(event) => update('maxDuration', Number(event.target.value))} /></label>
          </div>
          <label>默认抓取模式<select value={value.mode} onChange={(event) => update('mode', event.target.value as VideoGrabMode)}>{modeOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
          <label>默认 Cookie<textarea rows={2} value={value.cookie} placeholder="a=1; b=2" onChange={(event) => update('cookie', event.target.value)} /><small>需要登录才能看的网站用</small></label>
          <div className="video-settings-actions">
            <button className="secondary-button" type="button" onClick={onClose}>取消</button>
            <button className="primary-button" type="submit" disabled={saving}>{saving ? '保存中...' : '保存'}</button>
          </div>
        </form>
      ) : !error ? <p>正在读取设置...</p> : null}
    </section>
  )
}

function formatSize(bytes: number) {
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(0)} KB`
  if (bytes < 1073741824) return `${(bytes / 1048576).toFixed(1)} MB`
  return `${(bytes / 1073741824).toFixed(2)} GB`
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value))
}
