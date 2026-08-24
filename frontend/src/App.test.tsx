import { StrictMode } from 'react'
import { act, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'
import { SearchPage } from './features/search/SearchPage'
import { SettingsPage } from './features/settings/SettingsPage'
import { api, ApiError } from './lib/api'
import type { MTeamCheckinSettings } from './lib/types'

describe('App', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows administrator setup before protected pages', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ setup_required: true })

    render(<App />)

    expect(await screen.findByRole('heading', { name: '创建管理员密码' })).toBeInTheDocument()
  })

  it('preserves result overrides when async defaults arrive', async () => {
    const defaults = {
      category: 'series',
      save_paths: {
        movie: '/downloads/movies',
        tv: '/downloads/tv',
        music: '/downloads/music',
        other: '/downloads/other',
      },
      start: true,
    }
    let resolveDefaults!: (value: typeof defaults) => void
    const get = vi.spyOn(api, 'get').mockImplementation((path) =>
      path === '/api/settings/downloads'
        ? new Promise((resolve) => { resolveDefaults = resolve })
        : Promise.resolve({
            items: [
              {
                source_token: 'source-7',
                title: '三体',
                description: '2160p UHD BluRay',
                category: 'tv',
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

    await user.type(screen.getByRole('searchbox'), '三体')
    await user.click(screen.getByRole('button', { name: '搜索' }))
    await user.click(await screen.findByText('三体'))
    await user.clear(screen.getByLabelText('保存路径'))
    await user.type(screen.getByLabelText('保存路径'), '/downloads/custom-tv')
    await user.clear(screen.getByLabelText('qB 分类'))
    await user.type(screen.getByLabelText('qB 分类'), 'custom-series')
    await user.selectOptions(screen.getByLabelText('启动方式'), 'paused')

    await act(async () => { resolveDefaults(defaults) })

    expect(screen.getByLabelText('保存路径')).toHaveValue('/downloads/custom-tv')
    expect(screen.getByLabelText('qB 分类')).toHaveValue('custom-series')
    expect(screen.getByLabelText('启动方式')).toHaveValue('paused')
    await user.click(screen.getByRole('button', { name: '确认推送' }))

    expect(get).toHaveBeenCalledWith(expect.stringContaining('/api/search?'))
    expect(get).toHaveBeenCalledWith('/api/settings/downloads')
    expect(post).toHaveBeenCalledWith('/api/downloads', {
      source_token: 'source-7',
      category: 'custom-series',
      save_path: '/downloads/custom-tv',
      start: false,
    })
  })

  it('shows poster thumbnails and detail posters with safe image attributes', async () => {
    vi.spyOn(api, 'get').mockImplementation((path) =>
      path === '/api/settings/downloads'
        ? Promise.resolve({
            category: 'downloads',
            save_paths: { movie: '/downloads', tv: '/downloads', music: '/downloads', other: '/downloads' },
            start: true,
          })
        : Promise.resolve({
            items: [{
              source_token: 'source-poster',
              title: '海报电影',
              description: '2160p',
              category: 'movie',
              size: 1024,
              seeders: 1,
              leechers: 0,
              downloads: 0,
              download_factor: 1,
              upload_factor: 1,
              created_at: null,
              page_url: 'https://m-team.test/detail/poster',
              poster_url: 'https://images.m-team.test/poster.jpg',
              labels: [],
            }],
            page: 1,
            has_more: false,
          }),
    )
    const user = userEvent.setup()
    render(<SearchPage />)

    await user.type(screen.getByRole('searchbox'), '海报电影')
    await user.click(screen.getByRole('button', { name: '搜索' }))
    const thumbnail = await screen.findByAltText('海报电影 海报')
    expect(thumbnail).toHaveAttribute('src', 'https://images.m-team.test/poster.jpg')
    expect(thumbnail).toHaveAttribute('loading', 'lazy')
    expect(thumbnail).toHaveAttribute('decoding', 'async')
    expect(thumbnail).toHaveAttribute('referrerpolicy', 'no-referrer')
    expect(thumbnail).toHaveAttribute('aria-hidden', 'true')
    const titleButton = screen.getByRole('button', { name: '海报电影电影 · 2160p' })
    expect(titleButton).not.toHaveAccessibleName(/海报电影 海报/)

    await user.click(screen.getByText('海报电影'))

    const posters = screen.getAllByAltText('海报电影 海报')
    expect(posters).toHaveLength(2)
    expect(screen.getByRole('img', { name: '海报电影 海报' })).toBe(posters[1])
    expect(posters[1]).not.toHaveAttribute('aria-hidden')
  })

  it('uses a fixed fallback for missing and failed posters', async () => {
    vi.spyOn(api, 'get').mockImplementation((path) =>
      path === '/api/settings/downloads'
        ? Promise.resolve({
            category: 'downloads',
            save_paths: { movie: '/downloads', tv: '/downloads', music: '/downloads', other: '/downloads' },
            start: true,
          })
        : Promise.resolve({
            items: [
              {
                source_token: 'source-missing', title: '缺失海报', description: '', category: 'movie', size: 1,
                seeders: 1, leechers: 0, downloads: 0, download_factor: 1, upload_factor: 1,
                created_at: null, page_url: 'https://m-team.test/detail/missing', poster_url: null, labels: [],
              },
              {
                source_token: 'source-failed', title: '失败海报', description: '', category: 'movie', size: 1,
                seeders: 1, leechers: 0, downloads: 0, download_factor: 1, upload_factor: 1,
                created_at: null, page_url: 'https://m-team.test/detail/failed',
                poster_url: 'https://images.m-team.test/failed.jpg', labels: [],
              },
            ],
            page: 1,
            has_more: false,
          }),
    )
    const user = userEvent.setup()
    render(<SearchPage />)

    await user.type(screen.getByRole('searchbox'), '海报')
    await user.click(screen.getByRole('button', { name: '搜索' }))
    const missingThumbnail = await screen.findByTestId('poster-fallback')
    expect(missingThumbnail).toHaveAttribute('aria-hidden', 'true')
    expect(screen.queryByRole('img', { name: '缺失海报 海报不可用' })).not.toBeInTheDocument()

    await user.click(screen.getByText('缺失海报'))
    expect(screen.getByRole('img', { name: '缺失海报 海报不可用' })).toBeInTheDocument()
    expect(screen.getByText('缺失海报').closest('button')).not.toHaveAccessibleName(/海报不可用/)

    await user.click(screen.getByText('失败海报'))
    fireEvent.error(screen.getByRole('img', { name: '失败海报 海报' }))

    expect(screen.getByRole('img', { name: '失败海报 海报不可用' })).toBeInTheDocument()
    expect(screen.getByText('失败海报').closest('button')).not.toHaveAccessibleName(/海报不可用/)
  })

  it('recovers a failed poster when its source changes', async () => {
    let searchCount = 0
    vi.spyOn(api, 'get').mockImplementation((path) => {
      if (path === '/api/settings/downloads') {
        return Promise.resolve({
          category: 'downloads',
          save_paths: { movie: '/downloads', tv: '/downloads', music: '/downloads', other: '/downloads' },
          start: true,
        })
      }
      searchCount += 1
      return Promise.resolve({
        items: [{
          source_token: 'source-changing', title: '换源海报', description: '', category: 'movie', size: 1,
          seeders: 1, leechers: 0, downloads: 0, download_factor: 1, upload_factor: 1,
          created_at: null, page_url: 'https://m-team.test/detail/changing',
          poster_url: `https://images.m-team.test/poster-${searchCount}.jpg`, labels: [],
        }],
        page: 1,
        has_more: false,
      })
    })
    const user = userEvent.setup()
    render(<SearchPage />)

    await user.type(screen.getByRole('searchbox'), '换源海报')
    await user.click(screen.getByRole('button', { name: '搜索' }))
    fireEvent.error(await screen.findByAltText('换源海报 海报'))
    expect(screen.getByTestId('poster-fallback')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '搜索' }))

    expect(await screen.findByAltText('换源海报 海报')).toHaveAttribute(
      'src',
      'https://images.m-team.test/poster-2.jpg',
    )
  })

  it('uses the other path for a result with category all', async () => {
    vi.spyOn(api, 'get').mockImplementation((path) =>
      path === '/api/settings/downloads'
        ? Promise.resolve({
            category: 'misc',
            save_paths: {
              movie: '/downloads/movies',
              tv: '/downloads/tv',
              music: '/downloads/music',
              other: '/downloads/other',
            },
            start: true,
          })
        : Promise.resolve({
            items: [{
              source_token: 'source-other',
              title: '未分类资源',
              description: '',
              category: 'all',
              size: 1024,
              seeders: 1,
              leechers: 0,
              downloads: 0,
              download_factor: 1,
              upload_factor: 1,
              created_at: null,
              page_url: 'https://m-team.test/detail/other',
              labels: [],
            }],
            page: 1,
            has_more: false,
          }),
    )
    const user = userEvent.setup()
    render(<SearchPage />)

    await user.type(screen.getByRole('searchbox'), '未分类资源')
    await user.click(screen.getByRole('button', { name: '搜索' }))
    await user.click(await screen.findByText('未分类资源'))

    expect(screen.getByLabelText('保存路径')).toHaveValue('/downloads/other')
  })

  it('saves configurable qBittorrent download defaults', async () => {
    vi.spyOn(api, 'get').mockImplementation((path) =>
      path === '/api/settings/downloads'
        ? Promise.resolve({
            category: 'downloads',
            save_paths: {
              movie: '/downloads/movies',
              tv: '/downloads/tv',
              music: '/downloads/music',
              other: '/downloads/other',
            },
            start: true,
          })
        : Promise.resolve({ configured: false, masked: null, updated_at: null }),
    )
    const put = vi.spyOn(api, 'put').mockResolvedValue({
      category: 'media',
      save_paths: {
        movie: '/media/movies',
        tv: '/media/tv',
        music: '/media/music',
        other: '/media/other',
      },
      start: false,
    })
    const user = userEvent.setup()
    render(<SettingsPage />)

    await screen.findByDisplayValue('downloads')
    await user.clear(screen.getByLabelText('默认分类'))
    await user.type(screen.getByLabelText('默认分类'), 'media')
    expect(screen.getByLabelText('电影保存路径')).toHaveValue('/downloads/movies')
    expect(screen.getByLabelText('电视剧保存路径')).toHaveValue('/downloads/tv')
    expect(screen.getByLabelText('音乐保存路径')).toHaveValue('/downloads/music')
    expect(screen.getByLabelText('其他保存路径')).toHaveValue('/downloads/other')
    for (const [label, value] of [
      ['电影保存路径', '/media/movies'],
      ['电视剧保存路径', '/media/tv'],
      ['音乐保存路径', '/media/music'],
      ['其他保存路径', '/media/other'],
    ]) {
      await user.clear(screen.getByLabelText(label))
      await user.type(screen.getByLabelText(label), value)
    }
    await user.selectOptions(screen.getByLabelText('默认启动方式'), 'paused')
    await user.click(screen.getByRole('button', { name: '保存默认值' }))

    expect(put).toHaveBeenCalledWith('/api/settings/downloads', {
      category: 'media',
      save_paths: {
        movie: '/media/movies',
        tv: '/media/tv',
        music: '/media/music',
        other: '/media/other',
      },
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
        return Promise.resolve({
          category: 'downloads',
          save_paths: { movie: '/downloads', tv: '/downloads', music: '/downloads', other: '/downloads' },
          start: true,
        })
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
        return Promise.resolve({
          category: 'downloads',
          save_paths: { movie: '/downloads', tv: '/downloads', music: '/downloads', other: '/downloads' },
          start: true,
        })
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

  it('loads and saves M-Team daily check-in settings', async () => {
    const checkinSettings = {
      enabled: true,
      execution_time: '09:30',
      last_attempt_at: '2026-08-24T09:30:00',
      last_success_date: '2026-08-24',
      success: true,
      message: '签到成功',
    }
    const savedSettings = { ...checkinSettings, enabled: false, execution_time: '21:45' }
    const refreshedSettings = {
      ...savedSettings,
      last_attempt_at: '2026-08-25T21:45:00',
      last_success_date: null,
      success: false,
      message: '今日已签到',
    }
    let checkinGetCount = 0
    vi.spyOn(api, 'get').mockImplementation((path) => {
      if (path === '/api/settings/mteam/checkin') {
        checkinGetCount += 1
        return Promise.resolve(checkinGetCount === 1 ? checkinSettings : refreshedSettings)
      }
      if (path === '/api/settings/mteam') {
        return Promise.resolve({
          configured: true,
          masked: '••••••••',
          updated_at: null,
          base_url: 'https://m-team.example',
          headers: {},
          cookie: '••••••••',
          user_agent: null,
          timeout: 30,
        })
      }
      if (path === '/api/settings/downloads') {
        return Promise.resolve({
          category: 'downloads',
          save_paths: { movie: '/downloads', tv: '/downloads', music: '/downloads', other: '/downloads' },
          start: true,
        })
      }
      return Promise.resolve({ configured: false, masked: null, updated_at: null })
    })
    const put = vi.spyOn(api, 'put').mockResolvedValue(savedSettings)
    const user = userEvent.setup()
    render(<SettingsPage />)

    const enabled = await screen.findByLabelText('每日自动签到')
    expect(enabled).toBeChecked()
    expect(screen.getByLabelText('签到时间')).toHaveValue('09:30')
    expect(screen.getByText('最近签到成功')).toBeInTheDocument()
    expect(screen.getByText('2026/8/24 09:30:00')).toBeInTheDocument()
    expect(screen.getByText('签到成功')).toBeInTheDocument()

    await user.click(enabled)
    await user.clear(screen.getByLabelText('签到时间'))
    await user.type(screen.getByLabelText('签到时间'), '21:45')
    await user.click(screen.getByRole('button', { name: '保存签到设置' }))

    expect(put).toHaveBeenCalledWith('/api/settings/mteam/checkin', {
      enabled: false,
      execution_time: '21:45',
    })
    expect(await screen.findByText('最近签到失败')).toBeInTheDocument()
    expect(screen.getByText('2026/8/25 21:45:00')).toBeInTheDocument()
    expect(checkinGetCount).toBe(2)
  })

  it('keeps M-Team settings visible when check-in settings fail to load', async () => {
    vi.spyOn(api, 'get').mockImplementation((path) => {
      if (path === '/api/settings/mteam/checkin') return Promise.reject(new Error('check-in unavailable'))
      if (path === '/api/settings/mteam') {
        return Promise.resolve({
          configured: true,
          masked: '••••••••',
          updated_at: null,
          base_url: 'https://available-mteam.example',
          headers: {},
          cookie: '••••••••',
          user_agent: null,
          timeout: 30,
        })
      }
      if (path === '/api/settings/downloads') {
        return Promise.resolve({
          category: 'downloads',
          save_paths: { movie: '/downloads', tv: '/downloads', music: '/downloads', other: '/downloads' },
          start: true,
        })
      }
      if (path === '/api/settings/qbittorrent') {
        return Promise.resolve({ configured: true, masked: '••••••••', updated_at: null })
      }
      return Promise.resolve({ configured: false, masked: null, updated_at: null })
    })

    render(<SettingsPage />)

    expect(await screen.findByDisplayValue('https://available-mteam.example')).toBeInTheDocument()
    expect(screen.getByLabelText('默认分类')).toHaveValue('downloads')
    const qbSection = screen.getByRole('heading', { name: 'qBittorrent' }).closest('section')
    expect(qbSection).not.toBeNull()
    expect(within(qbSection!).getByText('已配置')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('签到设置加载失败')
  })

  it('retries a failed check-in settings request and restores the form', async () => {
    const checkinSettings = {
      enabled: true,
      execution_time: '08:45',
      last_attempt_at: null,
      last_success_date: null,
      success: null,
      message: null,
    }
    let attempts = 0
    vi.spyOn(api, 'get').mockImplementation((path) => {
      if (path === '/api/settings/mteam/checkin') {
        attempts += 1
        return attempts === 1
          ? Promise.reject(new ApiError('签到状态暂不可用', 503))
          : Promise.resolve(checkinSettings)
      }
      return Promise.reject(new Error(`${path} unavailable`))
    })
    const user = userEvent.setup()
    render(<SettingsPage />)

    expect(await screen.findByRole('alert')).toHaveTextContent('签到状态暂不可用')
    await user.click(screen.getByRole('button', { name: '重试加载签到设置' }))

    expect(await screen.findByLabelText('每日自动签到')).toBeChecked()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('syncs clean check-in controls when focus loads settings changed elsewhere', async () => {
    const initialSettings = {
      enabled: true,
      execution_time: '09:30',
      last_attempt_at: null,
      last_success_date: null,
      success: null,
      message: null,
    }
    const refreshedSettings = { ...initialSettings, enabled: false, execution_time: '18:20' }
    let checkinGetCount = 0
    vi.spyOn(api, 'get').mockImplementation((path) => {
      if (path !== '/api/settings/mteam/checkin') return Promise.reject(new Error(`${path} unavailable`))
      checkinGetCount += 1
      return Promise.resolve(checkinGetCount === 1 ? initialSettings : refreshedSettings)
    })
    render(<SettingsPage />)

    await screen.findByLabelText('每日自动签到')
    act(() => { window.dispatchEvent(new Event('focus')) })

    expect(await screen.findByDisplayValue('18:20')).toBeInTheDocument()
    expect(screen.getByLabelText('每日自动签到')).not.toBeChecked()
  })

  it('preserves dirty check-in controls when polling loads settings changed elsewhere', async () => {
    vi.useFakeTimers()
    const initialSettings = {
      enabled: true,
      execution_time: '09:30',
      last_attempt_at: null,
      last_success_date: null,
      success: null,
      message: null,
    }
    const refreshedSettings = { ...initialSettings, enabled: true, execution_time: '18:20' }
    let checkinGetCount = 0
    vi.spyOn(api, 'get').mockImplementation((path) => {
      if (path !== '/api/settings/mteam/checkin') return Promise.reject(new Error(`${path} unavailable`))
      checkinGetCount += 1
      return Promise.resolve(checkinGetCount === 1 ? initialSettings : refreshedSettings)
    })
    render(<SettingsPage />)

    await act(async () => undefined)
    fireEvent.click(screen.getByLabelText('每日自动签到'))
    fireEvent.change(screen.getByLabelText('签到时间'), { target: { value: '12:40' } })
    await act(async () => { await vi.advanceTimersByTimeAsync(30_000) })

    expect(screen.getByLabelText('每日自动签到')).not.toBeChecked()
    expect(screen.getByLabelText('签到时间')).toHaveValue('12:40')
  })

  it('resumes syncing check-in controls when refresh follows a successful save', async () => {
    const initialSettings = {
      enabled: true,
      execution_time: '09:30',
      last_attempt_at: null,
      last_success_date: null,
      success: null,
      message: null,
    }
    const savedSettings = { ...initialSettings, enabled: false, execution_time: '12:40' }
    const refreshedSettings = { ...savedSettings, enabled: true, execution_time: '20:15' }
    let checkinGetCount = 0
    vi.spyOn(api, 'get').mockImplementation((path) => {
      if (path !== '/api/settings/mteam/checkin') return Promise.reject(new Error(`${path} unavailable`))
      checkinGetCount += 1
      return Promise.resolve(checkinGetCount === 1 ? initialSettings : refreshedSettings)
    })
    vi.spyOn(api, 'put').mockResolvedValue(savedSettings)
    const user = userEvent.setup()
    render(<SettingsPage />)

    await screen.findByLabelText('每日自动签到')
    await user.click(screen.getByLabelText('每日自动签到'))
    await user.clear(screen.getByLabelText('签到时间'))
    await user.type(screen.getByLabelText('签到时间'), '12:40')
    await user.click(screen.getByRole('button', { name: '保存签到设置' }))

    expect(await screen.findByDisplayValue('20:15')).toBeInTheDocument()
    expect(screen.getByLabelText('每日自动签到')).toBeChecked()
  })

  it('coalesces overlapping check-in refreshes into one trailing request', async () => {
    vi.useFakeTimers()
    const initialSettings = {
      enabled: true,
      execution_time: '09:30',
      last_attempt_at: null,
      last_success_date: null,
      success: null,
      message: null,
    }
    const currentSettings = {
      ...initialSettings,
      last_attempt_at: '2026-08-24T09:30:00',
      success: false,
      message: '当前请求状态',
    }
    const newerSettings = {
      ...initialSettings,
      last_attempt_at: '2026-08-25T09:30:00',
      last_success_date: '2026-08-25',
      success: true,
      message: '新状态',
    }
    const pendingResolvers: Array<(value: MTeamCheckinSettings) => void> = []
    let checkinGetCount = 0
    let inFlight = 0
    let maxInFlight = 0
    let settledResolvers = 0
    vi.spyOn(api, 'get').mockImplementation((path) => {
      if (path !== '/api/settings/mteam/checkin') return Promise.reject(new Error(`${path} unavailable`))
      checkinGetCount += 1
      if (checkinGetCount === 1) return Promise.resolve(initialSettings)
      inFlight += 1
      maxInFlight = Math.max(maxInFlight, inFlight)
      return new Promise((resolve) => {
        pendingResolvers.push((value) => {
          inFlight -= 1
          resolve(value)
        })
      })
    })
    render(<SettingsPage />)

    try {
      await act(async () => undefined)
      fireEvent.click(screen.getByRole('button', { name: '刷新签到状态' }))
      await act(async () => { await vi.advanceTimersByTimeAsync(90_000) })
      act(() => { window.dispatchEvent(new Event('focus')) })
      expect(checkinGetCount).toBe(2)
      expect(maxInFlight).toBe(1)

      settledResolvers += 1
      await act(async () => { pendingResolvers[0](currentSettings) })
      expect(checkinGetCount).toBe(3)
      expect(screen.queryByText('当前请求状态')).not.toBeInTheDocument()

      settledResolvers += 1
      await act(async () => { pendingResolvers[1](newerSettings) })
      expect(checkinGetCount).toBe(3)
      expect(maxInFlight).toBe(1)
      expect(screen.getByText('新状态')).toBeInTheDocument()
    } finally {
      for (let attempts = 0; attempts < 10; attempts += 1) {
        const resolver = pendingResolvers[settledResolvers]
        if (!resolver) break
        settledResolvers += 1
        await act(async () => { resolver(newerSettings) })
      }
      vi.clearAllTimers()
    }
  })

  it('polls check-in settings while visible and clears polling on unmount', async () => {
    vi.useFakeTimers()
    const checkinSettings = {
      enabled: true,
      execution_time: '09:30',
      last_attempt_at: null,
      last_success_date: null,
      success: null,
      message: null,
    }
    let resolvePoll!: (value: typeof checkinSettings) => void
    let checkinGetCount = 0
    vi.spyOn(api, 'get').mockImplementation((path) => {
      if (path !== '/api/settings/mteam/checkin') return Promise.reject(new Error(`${path} unavailable`))
      checkinGetCount += 1
      return checkinGetCount === 1
        ? Promise.resolve(checkinSettings)
        : new Promise((resolve) => { resolvePoll = resolve })
    })
    const { unmount } = render(<SettingsPage />)
    await act(async () => undefined)
    expect(screen.getByLabelText('每日自动签到')).toBeInTheDocument()

    await act(async () => { await vi.advanceTimersByTimeAsync(30_000) })
    expect(checkinGetCount).toBe(2)
    unmount()
    await act(async () => { resolvePoll(checkinSettings) })
    await vi.advanceTimersByTimeAsync(30_000)
    expect(checkinGetCount).toBe(2)
  })

  it('does not refresh check-in state after a pending save resolves on unmount', async () => {
    const checkinSettings = {
      enabled: true,
      execution_time: '09:30',
      last_attempt_at: null,
      last_success_date: null,
      success: null,
      message: null,
    }
    let checkinGetCount = 0
    vi.spyOn(api, 'get').mockImplementation((path) => {
      if (path === '/api/settings/mteam/checkin') {
        checkinGetCount += 1
        return Promise.resolve(checkinSettings)
      }
      return Promise.reject(new Error(`${path} unavailable`))
    })
    let resolveSave!: (value: typeof checkinSettings) => void
    vi.spyOn(api, 'put').mockImplementation(
      () => new Promise((resolve) => { resolveSave = resolve }),
    )
    const user = userEvent.setup()
    const { unmount } = render(<SettingsPage />)

    await screen.findByLabelText('每日自动签到')
    await user.click(screen.getByRole('button', { name: '保存签到设置' }))
    unmount()
    await act(async () => { resolveSave(checkinSettings) })

    expect(checkinGetCount).toBe(1)
  })

  it('handles a check-in save after StrictMode replays effects', async () => {
    const checkinSettings = {
      enabled: true,
      execution_time: '09:30',
      last_attempt_at: null,
      last_success_date: null,
      success: null,
      message: null,
    }
    vi.spyOn(api, 'get').mockImplementation((path) =>
      path === '/api/settings/mteam/checkin'
        ? Promise.resolve(checkinSettings)
        : Promise.reject(new Error(`${path} unavailable`)),
    )
    vi.spyOn(api, 'put').mockResolvedValue(checkinSettings)
    const user = userEvent.setup()
    render(<StrictMode><SettingsPage /></StrictMode>)

    await screen.findByLabelText('每日自动签到')
    await user.click(screen.getByRole('button', { name: '保存签到设置' }))

    expect(await screen.findByText('签到设置已保存')).toBeInTheDocument()
  })

  it('shows an explicit fallback for an invalid check-in attempt time', async () => {
    vi.spyOn(api, 'get').mockImplementation((path) => {
      if (path === '/api/settings/mteam/checkin') {
        return Promise.resolve({
          enabled: true,
          execution_time: '09:30',
          last_attempt_at: 'not-a-date',
          last_success_date: null,
          success: false,
          message: '签到失败',
        })
      }
      return Promise.reject(new Error(`${path} unavailable`))
    })

    render(<SettingsPage />)

    expect(await screen.findByText('时间未知')).toBeInTheDocument()
  })

  it('disables check-in controls while saving and syncs the response', async () => {
    const initialSettings = {
      enabled: true,
      execution_time: '09:30',
      last_attempt_at: null,
      last_success_date: null,
      success: null,
      message: null,
    }
    const savedSettings = { ...initialSettings, enabled: false, execution_time: '21:45' }
    vi.spyOn(api, 'get').mockImplementation((path) => {
      if (path === '/api/settings/mteam/checkin') return Promise.resolve(initialSettings)
      return Promise.reject(new Error(`${path} unavailable`))
    })
    let resolveSave!: (value: typeof savedSettings) => void
    vi.spyOn(api, 'put').mockImplementation(
      () => new Promise((resolve) => { resolveSave = resolve }),
    )
    const user = userEvent.setup()
    render(<SettingsPage />)

    const enabled = await screen.findByLabelText('每日自动签到')
    await user.click(enabled)
    await user.clear(screen.getByLabelText('签到时间'))
    await user.type(screen.getByLabelText('签到时间'), '21:45')
    await user.click(screen.getByRole('button', { name: '保存签到设置' }))

    expect(enabled).toBeDisabled()
    expect(screen.getByLabelText('签到时间')).toBeDisabled()
    await act(async () => { resolveSave(savedSettings) })
    expect(enabled).toBeEnabled()
    expect(enabled).not.toBeChecked()
    expect(screen.getByLabelText('签到时间')).toBeEnabled()
    expect(screen.getByLabelText('签到时间')).toHaveValue('21:45')
  })

  it('restores check-in controls and shows a safe API error when saving fails', async () => {
    const checkinSettings = {
      enabled: true,
      execution_time: '09:30',
      last_attempt_at: null,
      last_success_date: null,
      success: null,
      message: null,
    }
    vi.spyOn(api, 'get').mockImplementation((path) => {
      if (path === '/api/settings/mteam/checkin') return Promise.resolve(checkinSettings)
      return Promise.reject(new Error(`${path} unavailable`))
    })
    let rejectSave!: (reason: Error) => void
    vi.spyOn(api, 'put').mockImplementation(
      () => new Promise((_, reject) => { rejectSave = reject }),
    )
    const user = userEvent.setup()
    render(<SettingsPage />)

    const enabled = await screen.findByLabelText('每日自动签到')
    await user.click(screen.getByRole('button', { name: '保存签到设置' }))
    expect(enabled).toBeDisabled()

    await act(async () => { rejectSave(new ApiError('签到配置保存失败', 400)) })
    expect(enabled).toBeEnabled()
    expect(screen.getByLabelText('签到时间')).toBeEnabled()
    expect(screen.getByRole('alert')).toHaveTextContent('签到配置保存失败')
  })

  it('shows a never-run status before the first check-in attempt', async () => {
    vi.spyOn(api, 'get').mockImplementation((path) => {
      if (path === '/api/settings/mteam/checkin') {
        return Promise.resolve({
          enabled: false,
          execution_time: '09:30',
          last_attempt_at: null,
          last_success_date: null,
          success: null,
          message: null,
        })
      }
      return Promise.reject(new Error(`${path} unavailable`))
    })

    render(<SettingsPage />)

    expect(await screen.findByText('尚未执行')).toBeInTheDocument()
  })
})
