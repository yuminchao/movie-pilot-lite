import { Download, LogOut, Radar, Search, Settings } from 'lucide-react'
import { BrowserRouter, NavLink, Navigate, Route, Routes, useNavigate } from 'react-router-dom'

import { AuthGuard } from './features/auth/AuthGuard'
import { DownloadsPage } from './features/downloads/DownloadsPage'
import { SearchPage } from './features/search/SearchPage'
import { SettingsPage } from './features/settings/SettingsPage'
import { api } from './lib/api'

export function App() {
  return (
    <BrowserRouter>
      <AuthGuard>
        <AppShell />
      </AuthGuard>
    </BrowserRouter>
  )
}

function AppShell() {
  const navigate = useNavigate()

  async function logout() {
    await api.post('/api/auth/logout')
    window.location.reload()
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <button className="brand" type="button" onClick={() => navigate('/search')}>
          <Radar size={20} />
          <span>movie-pilot-lite</span>
        </button>
        <nav aria-label="主导航">
          <NavLink to="/search"><Search size={17} />搜索</NavLink>
          <NavLink to="/downloads"><Download size={17} />下载任务</NavLink>
          <NavLink to="/settings"><Settings size={17} />设置</NavLink>
        </nav>
        <button className="icon-button logout" type="button" onClick={logout} title="退出登录">
          <LogOut size={17} />
        </button>
      </header>
      <Routes>
        <Route path="/search" element={<SearchPage />} />
        <Route path="/downloads" element={<DownloadsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/search" replace />} />
      </Routes>
    </div>
  )
}

