import type { ContentItem } from '../api/content'

export function contentMarkdown(item: ContentItem) {
  const title = item.title?.trim()
  const tags = item.tags?.length ? `\n\n标签：${item.tags.map(tag => `#${tag}`).join(' ')}` : ''
  return `${title ? `# ${title}\n\n` : ''}${item.content}${tags}\n`
}

export function contentFilename(item: ContentItem) {
  const title = (item.title || '未命名内容').replace(/[<>:"/\\|?*\u0000-\u001f]/g, '_').slice(0, 80).replace(/[. ]+$/, '')
  return `content-${item.id}-${title}.md`
}

export function downloadContent(item: ContentItem) {
  const url = URL.createObjectURL(new Blob([contentMarkdown(item)], { type: 'text/markdown;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = contentFilename(item)
  document.body.append(link)
  link.click()
  link.remove()
  // Give the browser time to consume the object URL before releasing it.
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
