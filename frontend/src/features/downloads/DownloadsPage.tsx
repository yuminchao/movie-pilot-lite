import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, CheckCircle2, Download, PauseCircle, RefreshCw } from 'lucide-react'

import { api, ApiError } from '../../lib/api'
import type { DownloadItem, DownloadPageData } from '../../lib/types'

type TaskFilter = 'all' | 'downloading' | 'completed' | 'paused'

export function DownloadsPage() {
  const [data, setData] = useState<DownloadPageData | null>(null)
  const [filter, setFilter] = useState<TaskFilter>('all')
  const [error, setError] = useState('')
  const [refreshing, setRefreshing] = useState(false)

  async function refresh() {
    setRefreshing(true)
    try {
      setData(await api.get<DownloadPageData>('/api/downloads'))
      setError('')
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : '无法读取 qBittorrent 任务')
    } finally {
      setRefreshing(false)
    }
  }

  useEffect(() => {
    void refresh()
    const timer = window.setInterval(refresh, 5000)
    return () => window.clearInterval(timer)
  }, [])

  const items = useMemo(
    () => (data?.items ?? []).filter((item) => filter === 'all' || item.status === filter),
    [data, filter],
  )

  return (
    <main className="page downloads-page">
      <div className="page-heading"><div><h1>下载任务</h1><p>只读查看 qBittorrent 实时状态和保存位置</p></div><button className="secondary-button" type="button" onClick={refresh} disabled={refreshing}><RefreshCw size={16} className={refreshing ? 'spinning' : ''} />刷新</button></div>
      <div className="task-toolbar">
        <div className="category-tabs">
          {(['all', 'downloading', 'completed', 'paused'] as TaskFilter[]).map((value) => <button key={value} type="button" className={filter === value ? 'active' : ''} onClick={() => setFilter(value)}>{value === 'all' ? '全部' : value === 'downloading' ? '下载中' : value === 'completed' ? '已完成' : '已暂停'}</button>)}
        </div>
        <span>{data?.stale ? 'qB 连接中断，显示上次状态' : data ? `更新于 ${new Date(data.refreshed_at).toLocaleTimeString('zh-CN')}` : '正在连接...'}</span>
      </div>
      {error ? <div className="alert error" role="alert">{error}</div> : null}
      {data?.stale ? <div className="alert warning"><AlertTriangle size={17} />qBittorrent 当前不可达，任务状态可能已过期。</div> : null}
      <section className="task-list">
        {items.map((item) => <TaskRow key={item.id} item={item} />)}
        {data && items.length === 0 ? <div className="empty-state"><Download size={28} /><strong>还没有下载任务</strong><span>从搜索结果推送资源后会显示在这里</span></div> : null}
      </section>
    </main>
  )
}

function TaskRow({ item }: { item: DownloadItem }) {
  const progress = Math.round((item.progress ?? 0) * 100)
  const Icon = item.status === 'completed' ? CheckCircle2 : item.status === 'paused' ? PauseCircle : Download
  return (
    <article className="task-row">
      <span className={`task-icon ${item.status}`}><Icon size={18} /></span>
      <div className="task-main"><div className="task-title"><strong>{item.title}</strong><span>{statusLabel(item.status)}</span></div><div className="progress-track"><span style={{ width: `${progress}%` }} /></div><div className="task-meta"><span>{progress}% · {formatSpeed(item.download_speed)} · {formatEta(item.eta)}</span><span>{item.save_path}</span></div></div>
    </article>
  )
}

function statusLabel(status: string) {
  return { downloading: '下载中', completed: '已完成', paused: '已暂停', queued: '已提交', error: '错误' }[status] ?? '未知'
}

function formatSpeed(value: number | null) {
  return value ? `${(value / 1024 / 1024).toFixed(1)} MiB/s` : '0 MiB/s'
}

function formatEta(value: number | null) {
  if (!value || value >= 8_640_000) return 'ETA --'
  return value < 3600 ? `ETA ${Math.ceil(value / 60)} 分钟` : `ETA ${(value / 3600).toFixed(1)} 小时`
}

