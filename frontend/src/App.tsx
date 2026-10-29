import { Download, LogOut, Radar, Search, Settings, Video } from 'lucide-react'
import { BrowserRouter, NavLink, Navigate, Route, Routes, useNavigate } from 'react-router-dom'

import { AuthGuard } from './features/auth/AuthGuard'
import { DownloadsPage } from './features/downloads/DownloadsPage'
import { SearchPage } from './features/search/SearchPage'
import { SettingsPage } from './features/settings/SettingsPage'
import { VideoPage } from './features/video/VideoPage'
import { api } from './lib/api'

export function App() {
  return (
    <BrowserRouter basename="/mpl">
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
      <aside className="sidebar">
        <button className="brand" type="button" onClick={() => navigate('/search')} title="movie-pilot-lite">
          <Radar size={20} />
          <span>movie-pilot-lite</span>
        </button>
        <nav aria-label="主导航">
          <NavLink to="/search"><Search size={17} /><span>搜索</span></NavLink>
          <NavLink to="/downloads"><Download size={17} /><span>下载任务</span></NavLink>
          <NavLink to="/video"><Video size={17} /><span>视频下载</span></NavLink>
          <NavLink to="/settings"><Settings size={17} /><span>设置</span></NavLink>
        </nav>
        <button className="icon-button logout" type="button" onClick={logout} title="退出登录">
          <LogOut size={17} />
          <span>退出登录</span>
        </button>
      </aside>
      <main className="app-main">
        <Routes>
          <Route path="/search" element={<SearchPage />} />
          <Route path="/downloads" element={<DownloadsPage />} />
          <Route path="/video" element={<VideoPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/search" replace />} />
        </Routes>
      </main>
    </div>
  )
}

