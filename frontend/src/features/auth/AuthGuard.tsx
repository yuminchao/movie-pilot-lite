import { FormEvent, ReactNode, useEffect, useState } from 'react'
import { LockKeyhole, Radar } from 'lucide-react'

import { api, ApiError } from '../../lib/api'
import type { AuthStatus } from '../../lib/types'

interface AuthGuardProps {
  children: ReactNode
}

export function AuthGuard({ children }: AuthGuardProps) {
  const [status, setStatus] = useState<AuthStatus | null>(null)
  const [authenticated, setAuthenticated] = useState(false)

  useEffect(() => {
    api
      .get<AuthStatus>('/api/auth/status')
      .then((value) => {
        setStatus(value)
        setAuthenticated(Boolean(value.authenticated))
      })
      .catch(() => setStatus({ setup_required: false }))
  }, [])

  if (!status) return <div className="fullscreen-status">正在检查服务状态...</div>
  if (!authenticated) {
    return (
      <AuthForm
        setupRequired={status.setup_required}
        onAuthenticated={() => setAuthenticated(true)}
      />
    )
  }
  return children
}

function AuthForm({
  setupRequired,
  onAuthenticated,
}: {
  setupRequired: boolean
  onAuthenticated: () => void
}) {
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError('')
    if (setupRequired && password !== confirmPassword) {
      setError('两次输入的密码不一致')
      return
    }
    setSubmitting(true)
    try {
      if (setupRequired) await api.post('/api/auth/setup', { password })
      await api.post('/api/auth/login', { password })
      onAuthenticated()
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : '无法连接服务')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="auth-layout">
      <section className="auth-brand">
        <div className="brand-mark"><Radar size={26} /></div>
        <h1>movie-pilot-lite</h1>
        <p>M-Team 资源检索与 qBittorrent 下载控制台</p>
      </section>
      <form className="auth-form" onSubmit={submit}>
        <LockKeyhole size={22} />
        <h2>{setupRequired ? '创建管理员密码' : '管理员登录'}</h2>
        <label>
          管理员密码
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            minLength={12}
            required
            autoFocus
          />
        </label>
        {setupRequired ? (
          <label>
            确认密码
            <input
              type="password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              minLength={12}
              required
            />
          </label>
        ) : null}
        {error ? <p className="form-error" role="alert">{error}</p> : null}
        <button className="primary-button" type="submit" disabled={submitting}>
          {submitting ? '正在处理...' : setupRequired ? '创建并登录' : '登录'}
        </button>
      </form>
    </main>
  )
}

