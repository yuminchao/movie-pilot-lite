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

export interface DownloadDefaults {
  category: string
  save_path: string
  start: boolean
}
