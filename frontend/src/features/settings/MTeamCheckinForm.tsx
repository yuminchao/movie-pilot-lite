import { FormEvent, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { CalendarClock, RefreshCw } from 'lucide-react'

import { api, ApiError } from '../../lib/api'
import type { MTeamCheckinSettings } from '../../lib/types'
import { formatCheckinTime } from './mteamCheckin'

interface MTeamCheckinFormProps {
  value: MTeamCheckinSettings | null
  loading: boolean
  refreshing: boolean
  loadError: string | null
  onRefresh: () => Promise<void>
}

export function MTeamCheckinForm({ value, loading, refreshing, loadError, onRefresh }: MTeamCheckinFormProps) {
  if (!value) {
    return (
      <CheckinSectionHeader refreshing={refreshing} retry={Boolean(loadError)} onRefresh={onRefresh}>
        {loadError
          ? <p className="checkin-load-state error" role="alert">{loadError}</p>
          : <p className="checkin-load-state" role="status">{loading ? '正在加载签到设置...' : '签到设置加载失败'}</p>}
      </CheckinSectionHeader>
    )
  }

  return (
    <CheckinSettingsForm
      value={value}
      refreshing={refreshing}
      loadError={loadError}
      onRefresh={onRefresh}
    />
  )
}

function CheckinSettingsForm({ value, refreshing, loadError, onRefresh }: Omit<MTeamCheckinFormProps, 'loading'> & { value: MTeamCheckinSettings }) {
  const [enabled, setEnabled] = useState(value.enabled)
  const [executionTime, setExecutionTime] = useState(value.execution_time)
  const [busy, setBusy] = useState(false)
  const [saveMessage, setSaveMessage] = useState('')
  const [saveFailed, setSaveFailed] = useState(false)
  const mounted = useRef(true)
  const dirty = useRef(false)
  const previousValue = useRef({ enabled: value.enabled, executionTime: value.execution_time })

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  useEffect(() => {
    const changed = previousValue.current.enabled !== value.enabled
      || previousValue.current.executionTime !== value.execution_time
    previousValue.current = { enabled: value.enabled, executionTime: value.execution_time }
    if (changed && !dirty.current && !busy) {
      setEnabled(value.enabled)
      setExecutionTime(value.execution_time)
    }
  }, [busy, value.enabled, value.execution_time])

  async function save(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setSaveMessage('')
    setSaveFailed(false)
    try {
      const result = await api.put<MTeamCheckinSettings>('/api/settings/mteam/checkin', {
        enabled,
        execution_time: executionTime,
      })
      if (!mounted.current) return
      setEnabled(result.enabled)
      setExecutionTime(result.execution_time)
      dirty.current = false
      setSaveMessage('签到设置已保存')
      void onRefresh()
    } catch (reason) {
      if (!mounted.current) return
      setSaveFailed(true)
      setSaveMessage(reason instanceof ApiError ? reason.message : '保存失败')
    } finally {
      if (mounted.current) setBusy(false)
    }
  }

  const statusLabel = value.success === null
    ? '尚未执行'
    : value.success
      ? '最近签到成功'
      : '最近签到失败'

  return (
    <CheckinSectionHeader refreshing={refreshing} retry={false} onRefresh={onRefresh}>
      <form className="checkin-form" onSubmit={save}>
        {loadError ? <p className="checkin-load-error" role="alert">{loadError}</p> : null}
        <div className="checkin-controls">
          <label className="checkin-toggle" htmlFor="mteam-checkin-enabled">
            <input
              id="mteam-checkin-enabled"
              type="checkbox"
              checked={enabled}
              onChange={(event) => {
                dirty.current = true
                setEnabled(event.target.checked)
              }}
              disabled={busy}
            />
            <span>每日自动签到</span>
          </label>
          <label htmlFor="mteam-checkin-time">
            签到时间
            <input
              id="mteam-checkin-time"
              type="time"
              value={executionTime}
              onChange={(event) => {
                dirty.current = true
                setExecutionTime(event.target.value)
              }}
              disabled={busy}
              required
            />
          </label>
        </div>
        <div className={`checkin-status ${value.success === true ? 'success' : value.success === false ? 'error' : ''}`} role="status">
          <strong>{statusLabel}</strong>
          {value.last_attempt_at ? <span>{formatCheckinTime(value.last_attempt_at)}</span> : null}
          {value.message ? <span className="checkin-status-message">{value.message}</span> : null}
        </div>
        <div className="form-actions">
          <button className="primary-button" type="submit" disabled={busy}>
            {busy ? '保存中...' : '保存签到设置'}
          </button>
        </div>
        {saveMessage ? (
          <p className={`settings-message ${saveFailed ? 'error' : ''}`} role={saveFailed ? 'alert' : 'status'}>
            {saveMessage}
          </p>
        ) : null}
      </form>
    </CheckinSectionHeader>
  )
}

function CheckinSectionHeader({
  refreshing,
  retry,
  onRefresh,
  children,
}: {
  refreshing: boolean
  retry: boolean
  onRefresh: () => Promise<void>
  children: ReactNode
}) {
  const label = retry ? '重试加载签到设置' : '刷新签到状态'
  return (
    <section className="settings-section checkin-section">
      <div className="section-title">
        <span className="section-icon checkin"><CalendarClock size={20} /></span>
        <div><h2>每日自动签到</h2><p>按设定时间执行 M-Team 每日签到</p></div>
        <button
          className="icon-button checkin-refresh"
          type="button"
          title={label}
          aria-label={label}
          onClick={() => { void onRefresh() }}
          disabled={refreshing}
        >
          <RefreshCw size={16} className={refreshing ? 'spinning' : ''} />
        </button>
      </div>
      {children}
    </section>
  )
}
