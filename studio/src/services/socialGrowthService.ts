import { apiClient } from './apiClient'

export type SocialPlatform = 'facebook' | 'instagram'
export type SocialDraftStatus = 'draft' | 'approved' | 'published' | 'rejected' | 'paused'

export interface SocialDraft {
  id: string
  platform: SocialPlatform
  body: string
  media_urls: string[]
  scheduled_for: string | null
  status: SocialDraftStatus
  approved_by: string | null
  created_at: string
  published_at: string | null
  audit: Array<{ event: string; actor_id: string }>
}

export const socialGrowthService = {
  listDrafts: () => apiClient.get<{ drafts: SocialDraft[] }>('/api/v1/social/drafts'),
  createDraft: (payload: { platform: SocialPlatform; body: string; media_urls?: string[]; scheduled_for?: string }) =>
    apiClient.post<{ draft: SocialDraft }>('/api/v1/social/drafts', payload),
  approveDraft: (draftId: string) =>
    apiClient.post<{ draft: SocialDraft; requires_browser_publish: boolean }>(`/api/v1/social/drafts/${encodeURIComponent(draftId)}/approve`, {}),
  pause: () => apiClient.post<{ status: string }>('/api/v1/social/pause', {}),
  resume: () => apiClient.post<{ status: string }>('/api/v1/social/resume', {}),
}

export default socialGrowthService
