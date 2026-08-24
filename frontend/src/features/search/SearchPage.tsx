import { FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import { ChevronDown, ChevronLeft, ChevronRight, Search, Send } from 'lucide-react'

import { api, ApiError } from '../../lib/api'
import type { Category, DownloadDefaults, SearchItem, SearchPageData, SearchSort } from '../../lib/types'

const categories: Array<{ value: Category; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'movie', label: '电影' },
  { value: 'tv', label: '电视剧' },
  { value: 'music', label: '音乐' },
]

export function SearchPage() {
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState<Category>('all')
  const [sort, setSort] = useState<SearchSort>('promotion')
  const [promotionOnly, setPromotionOnly] = useState(false)
  const [minimumSeeders, setMinimumSeeders] = useState(0)
  const [data, setData] = useState<SearchPageData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState<string | null>(null)
  const [notice, setNotice] = useState('')
  const [downloadDefaults, setDownloadDefaults] = useState<DownloadDefaults>({
    category: 'downloads',
    save_paths: {
      movie: '/downloads',
      tv: '/downloads',
      music: '/downloads',
      other: '/downloads',
    },
    start: true,
  })

  useEffect(() => {
    api
      .get<DownloadDefaults>('/api/settings/downloads')
      .then(setDownloadDefaults)
      .catch(() => undefined)
  }, [])

  const visibleItems = useMemo(
    () =>
      (data?.items ?? []).filter(
        (item) => item.seeders >= minimumSeeders && (!promotionOnly || item.download_factor < 1),
      ),
    [data, minimumSeeders, promotionOnly],
  )

  async function runSearch(page = 1) {
    if (!query.trim()) return
    setLoading(true)
    setError('')
    setNotice('')
    const params = new URLSearchParams({
      q: query.trim(),
      category,
      page: String(page),
      sort,
    })
    try {
      setData(await api.get<SearchPageData>(`/api/search?${params}`))
      setExpanded(null)
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : '搜索请求失败')
    } finally {
      setLoading(false)
    }
  }

  function submitSearch(event: FormEvent) {
    event.preventDefault()
    void runSearch(1)
  }

  return (
    <main className="page search-page">
      <form className="search-command" onSubmit={submitSearch}>
        <Search size={20} />
        <input
          type="search"
          placeholder="输入片名、剧名、音乐专辑或 IMDb ID"
          aria-label="搜索关键词"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <button className="primary-button" type="submit" disabled={loading}>
          {loading ? '搜索中...' : '搜索'}
        </button>
      </form>
      <div className="search-toolbar">
        <div className="category-tabs" role="tablist" aria-label="资源垂类">
          {categories.map((item) => (
            <button
              key={item.value}
              type="button"
              className={category === item.value ? 'active' : ''}
              onClick={() => setCategory(item.value)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <div className="filters">
          <label><input type="checkbox" checked={promotionOnly} onChange={(event) => setPromotionOnly(event.target.checked)} />仅促销</label>
          <label>最小做种<input className="compact-input" type="number" min="0" value={minimumSeeders} onChange={(event) => setMinimumSeeders(Number(event.target.value))} /></label>
          <label>排序<select value={sort} onChange={(event) => setSort(event.target.value as SearchSort)}><option value="promotion">免费优先</option><option value="seeders">做种最多</option><option value="newest">最新发布</option></select></label>
        </div>
      </div>
      {error ? <div className="alert error" role="alert">{error}</div> : null}
      {notice ? <div className="alert success" role="status">{notice}</div> : null}
      <section className="results-surface" aria-live="polite">
        <div className="results-meta">
          <span>{data ? `${visibleItems.length} 条结果` : '等待搜索'}</span>
          {data ? <span>第 {data.page} 页</span> : null}
        </div>
        <div className="result-table" role="table" aria-label="搜索结果">
          <div className="result-header" role="row">
            <span>资源名称</span><span>大小</span><span>做种</span><span>促销</span><span>发布时间</span><span aria-hidden="true"></span>
          </div>
          {visibleItems.map((item) => (
            <ResultRow
              key={item.source_token}
              item={item}
              expanded={expanded === item.source_token}
              onToggle={() => setExpanded(expanded === item.source_token ? null : item.source_token)}
              onSuccess={() => setNotice(`已将「${item.title}」推送到 qBittorrent`)}
              defaults={downloadDefaults}
            />
          ))}
        </div>
        {data && visibleItems.length === 0 ? <div className="empty-state"><Search size={28} /><strong>没有符合筛选条件的资源</strong><span>调整垂类、促销或做种数后重试</span></div> : null}
        {!data ? <div className="empty-state"><Search size={28} /><strong>输入关键词开始搜索</strong><span>支持电影、电视剧、音乐和 IMDb ID</span></div> : null}
        {data ? (
          <div className="pagination">
            <button type="button" className="icon-button" disabled={data.page <= 1} onClick={() => runSearch(data.page - 1)} title="上一页"><ChevronLeft size={18} /></button>
            <span>第 {data.page} 页</span>
            <button type="button" className="icon-button" disabled={!data.has_more} onClick={() => runSearch(data.page + 1)} title="下一页"><ChevronRight size={18} /></button>
          </div>
        ) : null}
      </section>
    </main>
  )
}

function ResultRow({ item, expanded, onToggle, onSuccess, defaults }: { item: SearchItem; expanded: boolean; onToggle: () => void; onSuccess: () => void; defaults: DownloadDefaults }) {
  const [qbCategory, setQbCategory] = useState(defaults.category)
  const [savePath, setSavePath] = useState(() => defaultSavePath(item.category, defaults))
  const [start, setStart] = useState(defaults.start)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const categoryEdited = useRef(false)
  const savePathEdited = useRef(false)
  const startEdited = useRef(false)

  useEffect(() => {
    if (!categoryEdited.current) setQbCategory(defaults.category)
    if (!savePathEdited.current) setSavePath(defaultSavePath(item.category, defaults))
    if (!startEdited.current) setStart(defaults.start)
  }, [defaults, item.category])

  async function push() {
    setSending(true)
    setError('')
    try {
      await api.post('/api/downloads', { source_token: item.source_token, category: qbCategory, save_path: savePath, start })
      onSuccess()
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : '推送失败')
    } finally {
      setSending(false)
    }
  }

  return (
    <div className={`result-group ${expanded ? 'expanded' : ''}`}>
      <div className="result-row" role="row">
        <button className="result-title" type="button" onClick={onToggle} aria-expanded={expanded}>
          <span><strong>{item.title}</strong><small>{item.category === 'tv' ? '电视剧' : item.category === 'music' ? '音乐' : '电影'} · {item.description || item.labels.join(' · ')}</small></span>
          <ChevronDown size={17} />
        </button>
        <span data-label="大小">{formatBytes(item.size)}</span>
        <span data-label="做种">{item.seeders}</span>
        <span data-label="促销"><Promotion factor={item.download_factor} upload={item.upload_factor} /></span>
        <span data-label="发布">{formatDate(item.created_at)}</span>
        <button className="secondary-button" type="button" onClick={onToggle}>推送</button>
      </div>
      {expanded ? (
        <div className="download-options">
          <label>qB 分类<input value={qbCategory} onChange={(event) => { categoryEdited.current = true; setQbCategory(event.target.value) }} /></label>
          <label>保存路径<input value={savePath} onChange={(event) => { savePathEdited.current = true; setSavePath(event.target.value) }} /></label>
          <label>启动方式<select value={start ? 'start' : 'paused'} onChange={(event) => { startEdited.current = true; setStart(event.target.value === 'start') }}><option value="start">立即开始</option><option value="paused">暂停添加</option></select></label>
          <button className="primary-button push-button" type="button" disabled={sending} onClick={push}><Send size={16} />{sending ? '推送中...' : '确认推送'}</button>
          {error ? <p className="inline-error" role="alert">{error}</p> : null}
        </div>
      ) : null}
    </div>
  )
}

function defaultSavePath(category: Category, defaults: DownloadDefaults) {
  if (category === 'movie' || category === 'tv' || category === 'music') {
    return defaults.save_paths[category]
  }
  return defaults.save_paths.other
}

function Promotion({ factor, upload }: { factor: number; upload: number }) {
  if (factor === 0) return <strong className="promotion free">FREE{upload > 1 ? ' · 2X' : ''}</strong>
  if (factor < 1) return <strong className="promotion discount">{Math.round(factor * 100)}%</strong>
  return <span className="promotion normal">普通</span>
}

function formatBytes(bytes: number) {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / 1024 ** index).toFixed(index > 2 ? 1 : 0)} ${units[index]}`
}

function formatDate(value: string | null) {
  if (!value) return '未知'
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value))
}
