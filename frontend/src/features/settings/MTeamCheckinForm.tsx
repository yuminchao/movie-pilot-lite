import { FormEvent, useState } from 'react'
import { CalendarClock } from 'lucide-react'

import { api, ApiError } from '../../lib/api'
import type { MTeamCheckinSettings } from '../../lib/types'

export function MTeamCheckinForm({ value }: { value: MTeamCheckinSettings }) {
  const [settings, setSettings] = useState(value)
  const [enabled, setEnabled] = useState(value.enabled)
  const [executionTime, setExecutionTime] = useState(value.execution_time)
  const [busy, setBusy] = useState(false)
  const [saveMessage, setSaveMessage] = useState('')
  const [saveFailed, setSaveFailed] = useState(false)

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
      setSettings(result)
      setEnabled(result.enabled)
      setExecutionTime(result.execution_time)
      setSaveMessage('签到设置已保存')
    } catch (reason) {
      setSaveFailed(true)
      setSaveMessage(reason instanceof ApiError ? reason.message : '保存失败')
    } finally {
      setBusy(false)
    }
  }

  const statusLabel = settings.success === null
    ? '尚未执行'
    : settings.success
      ? '最近签到成功'
      : '最近签到失败'

  return (
    <section className="settings-section checkin-section">
      <div className="section-title">
        <span className="section-icon checkin"><CalendarClock size={20} /></span>
        <div><h2>每日自动签到</h2><p>按设定时间执行 M-Team 每日签到</p></div>
      </div>
      <form className="checkin-form" onSubmit={save}>
        <div className="checkin-controls">
          <label className="checkin-toggle" htmlFor="mteam-checkin-enabled">
            <input
              id="mteam-checkin-enabled"
              type="checkbox"
              checked={enabled}
              onChange={(event) => setEnabled(event.target.checked)}
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
              onChange={(event) => setExecutionTime(event.target.value)}
              disabled={busy}
              required
            />
          </label>
        </div>
        <div className={`checkin-status ${settings.success === true ? 'success' : settings.success === false ? 'error' : ''}`} role="status">
          <strong>{statusLabel}</strong>
          {settings.last_attempt_at ? <span>{new Date(settings.last_attempt_at).toLocaleString('zh-CN')}</span> : null}
          {settings.message ? <span className="checkin-status-message">{settings.message}</span> : null}
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
    </section>
  )
}
