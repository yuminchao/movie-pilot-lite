export type Category = 'all' | 'movie' | 'tv' | 'music'
export type SearchSort = 'promotion' | 'seeders' | 'newest'

export interface AuthStatus {
  setup_required: boolean
  authenticated?: boolean
}

export interface SearchItem {
  source_token: string
  title: string
  description: string
  category: Category
  size: number
  seeders: number
  leechers: number
  downloads: number
  download_factor: number
  upload_factor: number
  created_at: string | null
  page_url: string
  poster_url: string | null
  labels: string[]
}

export interface SearchPageData {
  items: SearchItem[]
  page: number
  has_more: boolean
}

export interface MaskedSettings {
  configured: boolean
  masked: string | null
  updated_at: string | null
}

export interface MTeamSettings extends MaskedSettings {
  base_url: string
  headers: Record<string, string>
  cookie: string | null
  user_agent: string | null
  timeout: number
}

export interface MTeamCheckinSettings {
  enabled: boolean
  execution_time: string
  last_attempt_at: string | null
  last_success_date: string | null
  success: boolean | null
  message: string | null
}

export interface DownloadItem {
  id: number
  title: string
  qb_hash: string | null
  category: string | null
  save_path: string
  status: string
  progress: number | null
  download_speed: number | null
  eta: number | null
  created_at: string
}

export interface DownloadPageData {
  items: DownloadItem[]
  stale: boolean
  refreshed_at: string
}

export interface DownloadPaths {
  movie: string
  tv: string
  music: string
  other: string
}

export interface DownloadDefaults {
  category: string
  save_paths: DownloadPaths
  start: boolean
}
