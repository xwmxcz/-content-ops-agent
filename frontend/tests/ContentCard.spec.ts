import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ContentCard from '../src/components/ContentCard.vue'
import type { ContentItem } from '../src/api/content'

function item(overrides: Partial<ContentItem> = {}): ContentItem {
  return {
    id: 7,
    title: '春季新品种草',
    content: '正文内容',
    content_type: 'xiaohongshu',
    style: 'marketing',
    status: 'draft',
    created_at: '2025-01-13T10:20:30',
    ...overrides
  }
}

describe('ContentCard', () => {
  it('renders the human-readable type, style and status labels', () => {
    const wrapper = mount(ContentCard, { props: { item: item() } })

    expect(wrapper.text()).toContain('小红书')
    expect(wrapper.text()).toContain('营销')
    expect(wrapper.text()).toContain('草稿')
  })

  it('falls back to a placeholder title when none is set', () => {
    const wrapper = mount(ContentCard, { props: { item: item({ title: undefined }) } })

    expect(wrapper.text()).toContain('未命名内容')
  })

  it('shows the id and the date portion of created_at', () => {
    const wrapper = mount(ContentCard, { props: { item: item() } })

    expect(wrapper.text()).toContain('#7')
    expect(wrapper.text()).toContain('2025-01-13')
  })

  it('distinguishes updated content from new content', () => {
    const fresh = mount(ContentCard, { props: { item: item() } })
    expect(fresh.text()).toContain('新内容')

    const edited = mount(ContentCard, {
      props: { item: item({ updated_at: '2025-01-14T08:00:00' }) }
    })
    expect(edited.text()).toContain('已更新')
  })

  it('passes through unknown enum values rather than hiding them', () => {
    const wrapper = mount(ContentCard, {
      props: { item: item({ content_type: 'podcast', status: 'weird' }) }
    })

    expect(wrapper.text()).toContain('podcast')
    expect(wrapper.text()).toContain('weird')
  })

  it('renders without a created_at timestamp', () => {
    const wrapper = mount(ContentCard, { props: { item: item({ created_at: undefined }) } })

    expect(wrapper.text()).toContain('-')
  })
})
