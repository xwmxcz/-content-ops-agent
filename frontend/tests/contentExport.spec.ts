import { describe, expect, it } from 'vitest'
import { contentFilename, contentMarkdown } from '../src/utils/contentExport'

describe('content export', () => {
  it('exports full Unicode text and tags with a portable filename', () => {
    const item = { id: 13, title: '选题/运营:😀', content: '正文\n'.repeat(1000), tags: ['品牌', '运营'], content_type: 'blog', style: 'casual', status: 'draft' }
    expect(contentMarkdown(item)).toContain(item.content)
    expect(contentMarkdown(item)).toContain('# 选题/运营:😀')
    expect(contentMarkdown(item)).toContain('#品牌 #运营')
    expect(contentFilename(item)).toBe('content-13-选题_运营_😀.md')
  })
})
