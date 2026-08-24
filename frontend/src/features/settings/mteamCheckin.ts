import { api } from '../../lib/api'
import type { MTeamCheckinSettings } from '../../lib/types'

export function loadCheckinSettings() {
  return api.get<MTeamCheckinSettings>('/api/settings/mteam/checkin')
}

export function formatCheckinTime(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '时间未知' : date.toLocaleString('zh-CN')
}
