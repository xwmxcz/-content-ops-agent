export const CONTENT_TYPE_OPTIONS = [
  { label: '小红书', value: 'xiaohongshu' },
  { label: '微博', value: 'weibo' },
  { label: '博客文章', value: 'blog' },
  { label: '视频脚本', value: 'video_script' },
  { label: 'Twitter / X', value: 'twitter' }
] as const

export const STYLE_OPTIONS = [
  { label: '专业', value: 'professional' },
  { label: '轻松', value: 'casual' },
  { label: '营销', value: 'marketing' },
  { label: '故事', value: 'storytelling' }
] as const

export const LENGTH_OPTIONS = [
  { label: '短', value: 'short' },
  { label: '中', value: 'medium' },
  { label: '长', value: 'long' }
] as const

export const STATUS_LABELS: Record<string, string> = {
  draft: '草稿',
  refined: '已打磨',
  published: '已发布',
  archived: '已归档',
  agent_final: 'Agent 成稿'
}

export function getContentTypeLabel(value?: string) {
  return CONTENT_TYPE_OPTIONS.find(item => item.value === value)?.label ?? value ?? '未知类型'
}

export function getStyleLabel(value?: string) {
  return STYLE_OPTIONS.find(item => item.value === value)?.label ?? value ?? '未设置'
}

export function getStatusLabel(value?: string) {
  return STATUS_LABELS[value ?? ''] ?? value ?? '未知状态'
}
