import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'
import { SearchPage } from './features/search/SearchPage'
import { SettingsPage } from './features/settings/SettingsPage'
import { api } from './lib/api'

describe('App', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('shows administrator setup before protected pages', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ setup_required: true })

    render(<App />)

    expect(await screen.findByRole('heading', { name: '创建管理员密码' })).toBeInTheDocument()
  })

  it('expands a result and submits qBittorrent options', async () => {
    const get = vi.spyOn(api, 'get').mockImplementation((path) =>
      path === '/api/settings/downloads'
        ? Promise.resolve({ category: 'movies', save_path: '/downloads/movies', start: true })
        : Promise.resolve({
            items: [
              {
                source_token: 'source-7',
                title: '流浪地球 2',
                description: '2160p UHD BluRay',
                category: 'movie',
                size: 30_708_154_982,
                seeders: 126,
                leechers: 8,
                downloads: 420,
                download_factor: 0,
                upload_factor: 1,
                created_at: '2026-08-23T10:00:00Z',
                page_url: 'https://m-team.test/detail/7',
                labels: ['国语', '中字'],
              },
            ],
            page: 1,
            has_more: false,
          }),
    )
    const post = vi.spyOn(api, 'post').mockResolvedValue({ status: 'queued' })
    const user = userEvent.setup()
    render(<SearchPage />)

    await user.type(screen.getByRole('searchbox'), '流浪地球 2')
    await user.click(screen.getByRole('button', { name: '搜索' }))
    await user.click(await screen.findByText('流浪地球 2'))
    expect(screen.getByLabelText('保存路径')).toBeVisible()
    await user.click(screen.getByRole('button', { name: '确认推送' }))

    expect(get).toHaveBeenCalledWith(expect.stringContaining('/api/search?'))
    expect(get).toHaveBeenCalledWith('/api/settings/downloads')
    expect(post).toHaveBeenCalledWith('/api/downloads', {
      source_token: 'source-7',
      category: 'movies',
      save_path: '/downloads/movies',
      start: true,
    })
  })

  it('saves configurable qBittorrent download defaults', async () => {
    vi.spyOn(api, 'get').mockImplementation((path) =>
      path === '/api/settings/downloads'
        ? Promise.resolve({ category: 'downloads', save_path: '/downloads', start: true })
        : Promise.resolve({ configured: false, masked: null, updated_at: null }),
    )
    const put = vi.spyOn(api, 'put').mockResolvedValue({
      category: 'media',
      save_path: '/downloads/media',
      start: false,
    })
    const user = userEvent.setup()
    render(<SettingsPage />)

    await screen.findByDisplayValue('downloads')
    await user.clear(screen.getByLabelText('默认分类'))
    await user.type(screen.getByLabelText('默认分类'), 'media')
    await user.clear(screen.getByLabelText('默认保存路径'))
    await user.type(screen.getByLabelText('默认保存路径'), '/downloads/media')
    await user.selectOptions(screen.getByLabelText('默认启动方式'), 'paused')
    await user.click(screen.getByRole('button', { name: '保存默认值' }))

    expect(put).toHaveBeenCalledWith('/api/settings/downloads', {
      category: 'media',
      save_path: '/downloads/media',
      start: false,
    })
  })

  it('echoes masked M-Team settings and preserves them when saving', async () => {
    const mteamSettings = {
      configured: true,
      masked: '••••••••',
      updated_at: '2026-08-24T12:00:00Z',
      base_url: 'https://m-team.example',
      headers: {
        'x-api-key': '••••••••',
        authorization: '••••••••',
      },
      cookie: '••••••••',
      user_agent: 'custom-agent/2.0',
      timeout: 37,
    }
    vi.spyOn(api, 'get').mockImplementation((path) => {
      if (path === '/api/settings/mteam') return Promise.resolve(mteamSettings)
      if (path === '/api/settings/downloads') {
        return Promise.resolve({ category: 'downloads', save_path: '/downloads', start: true })
      }
      return Promise.resolve({ configured: false, masked: null, updated_at: null })
    })
    const put = vi.spyOn(api, 'put').mockResolvedValue(mteamSettings)
    const user = userEvent.setup()
    render(<SettingsPage />)

    expect(await screen.findByDisplayValue('https://m-team.example')).toBeInTheDocument()
    expect(screen.getByDisplayValue('custom-agent/2.0')).toBeInTheDocument()
    expect(screen.getByDisplayValue('37')).toBeInTheDocument()
    expect(screen.getByLabelText('Header JSON')).toHaveValue(
      JSON.stringify(mteamSettings.headers, null, 2),
    )
    expect(screen.getByLabelText('Cookie')).toHaveValue('••••••••')

    await user.click(screen.getAllByRole('button', { name: '保存配置' })[0])

    expect(put).toHaveBeenCalledWith('/api/settings/mteam', {
      base_url: 'https://m-team.example',
      headers: mteamSettings.headers,
      cookie: '••••••••',
      user_agent: 'custom-agent/2.0',
      timeout: 37,
    })
  })

  it('shows M-Team settings when other settings requests fail', async () => {
    const mteamSettings = {
      configured: true,
      masked: '••••••••',
      updated_at: '2026-08-24T12:00:00Z',
      base_url: 'https://available-mteam.example',
      headers: { 'x-api-key': '••••••••' },
      cookie: '••••••••',
      user_agent: 'custom-agent/2.0',
      timeout: 37,
    }
    vi.spyOn(api, 'get').mockImplementation((path) => {
      if (path === '/api/settings/mteam') return Promise.resolve(mteamSettings)
      return Promise.reject(new Error(`${path} unavailable`))
    })

    render(<SettingsPage />)

    expect(
      await screen.findByDisplayValue('https://available-mteam.example'),
    ).toBeInTheDocument()
  })

  it('disables M-Team fields while saving and syncs the response', async () => {
    const initialSettings = {
      configured: true,
      masked: '••••••••',
      updated_at: '2026-08-24T12:00:00Z',
      base_url: 'https://m-team.example',
      headers: { 'x-api-key': '••••••••' },
      cookie: '••••••••',
      user_agent: 'custom-agent/2.0',
      timeout: 37,
    }
    const savedSettings = {
      ...initialSettings,
      updated_at: '2026-08-24T12:01:00Z',
      base_url: 'https://saved-mteam.example',
    }
    vi.spyOn(api, 'get').mockImplementation((path) => {
      if (path === '/api/settings/mteam') return Promise.resolve(initialSettings)
      if (path === '/api/settings/downloads') {
        return Promise.resolve({ category: 'downloads', save_path: '/downloads', start: true })
      }
      return Promise.resolve({ configured: false, masked: null, updated_at: null })
    })
    let resolveSave!: (value: typeof savedSettings) => void
    vi.spyOn(api, 'put').mockImplementation(
      () => new Promise((resolve) => { resolveSave = resolve }),
    )
    const user = userEvent.setup()
    render(<SettingsPage />)

    await screen.findByDisplayValue(initialSettings.base_url)
    await user.click(screen.getAllByRole('button', { name: '保存配置' })[0])

    expect(screen.getByLabelText('站点地址')).toBeDisabled()
    expect(screen.getByLabelText('Header JSON')).toBeDisabled()
    expect(screen.getByLabelText('Cookie')).toBeDisabled()
    expect(screen.getByLabelText('User-Agent')).toBeDisabled()
    expect(screen.getByLabelText('请求超时（秒）')).toBeDisabled()

    await act(async () => { resolveSave(savedSettings) })

    expect(await screen.findByDisplayValue(savedSettings.base_url)).toBeEnabled()
    expect(screen.getByLabelText('Header JSON')).toBeEnabled()
    expect(screen.getByLabelText('Cookie')).toBeEnabled()
    expect(screen.getByLabelText('User-Agent')).toBeEnabled()
    expect(screen.getByLabelText('请求超时（秒）')).toBeEnabled()
  })
})
