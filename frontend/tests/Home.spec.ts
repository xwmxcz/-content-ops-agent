import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount, type VueWrapper } from '@vue/test-utils'
import Home from '../src/views/Home.vue'

const api = vi.hoisted(() => ({ getContents: vi.fn(), getStats: vi.fn() }))
vi.mock('../src/api/content', () => api)
vi.mock('../src/api/stats', () => api)
const stats = { total_contents: 42, by_type: { blog: 42 }, by_status: { draft: 42 } }
const content = { id: 1, title: '已有稿件', content: '正文', content_type: 'blog', style: 'professional', status: 'draft', created_at: '2026-09-29T10:00:00' }
const wrappers: VueWrapper[] = []

function mountHome() {
  const wrapper = shallowMount(Home, {
    global: { stubs: { 'el-button': { template: '<button><slot /></button>' } } }
  })
  wrappers.push(wrapper)
  return wrapper
}
function button(wrapper: VueWrapper, text: string) {
  return wrapper.findAll('button').find(item => item.text() === text)!
}
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}

beforeEach(() => {
  api.getContents.mockReset().mockResolvedValue([content])
  api.getStats.mockReset().mockResolvedValue(stats)
})
afterEach(() => { wrappers.splice(0).forEach(wrapper => wrapper.unmount()) })

describe('home independent loading states', () => {
  it('does not display unknown totals as zero or pending content as an empty library', async () => {
    const pendingStats = deferred<typeof stats>()
    const pendingContent = deferred<typeof content[]>()
    api.getStats.mockReturnValueOnce(pendingStats.promise)
    api.getContents.mockReturnValueOnce(pendingContent.promise)
    const wrapper = mountHome()
    await flushPromises()

    expect(wrapper.find('.metric-card strong').text()).toBe('—')
    expect(wrapper.find('[description="暂无内容"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('内容加载中')
    pendingStats.resolve({ total_contents: 0, by_type: {}, by_status: {} })
    pendingContent.resolve([])
    await flushPromises()
    expect(wrapper.find('.metric-card strong').text()).toBe('0')
    expect(wrapper.find('[description="暂无内容"]').exists()).toBe(true)
  })

  it('keeps recent content usable when stats fail, and retries only stats', async () => {
    api.getStats.mockRejectedValueOnce(new Error('统计服务离线'))
    const wrapper = mountHome()
    await flushPromises()

    expect(wrapper.find('[role="alert"]').text()).toContain('统计服务离线')
    expect(wrapper.find('.metric-card strong').text()).toBe('—')
    expect(wrapper.findAll('content-card-stub')).toHaveLength(1)
    await button(wrapper, '重试统计').trigger('click')
    await flushPromises()
    expect(wrapper.find('.metric-card strong').text()).toBe('42')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(api.getStats).toHaveBeenCalledTimes(2)
    expect(api.getContents).toHaveBeenCalledOnce()
  })

  it('keeps stats usable when recent content fails without claiming the library is empty', async () => {
    api.getContents.mockRejectedValueOnce(new Error('内容服务离线'))
    const wrapper = mountHome()
    await flushPromises()

    expect(wrapper.find('.metric-card strong').text()).toBe('42')
    expect(wrapper.find('[role="alert"]').text()).toContain('内容服务离线')
    expect(wrapper.find('[description="暂无内容"]').exists()).toBe(false)
    await button(wrapper, '重试内容').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('content-card-stub')).toHaveLength(1)
    expect(api.getContents).toHaveBeenCalledTimes(2)
    expect(api.getStats).toHaveBeenCalledOnce()
  })

  it('retains successful data and labels it as previous data when refreshing fails', async () => {
    const wrapper = mountHome()
    await flushPromises()
    api.getStats.mockRejectedValueOnce(new Error('暂时失败'))
    api.getContents.mockRejectedValueOnce(new Error('暂时失败'))
    await button(wrapper, '刷新统计').trigger('click')
    await button(wrapper, '刷新内容').trigger('click')
    await flushPromises()

    expect(wrapper.find('.metric-card strong').text()).toBe('42')
    expect(wrapper.findAll('content-card-stub')).toHaveLength(1)
    expect(wrapper.findAll('[role="alert"]')).toHaveLength(2)
    expect(wrapper.findAll('[role="alert"]').every(alert => alert.text().includes('上次加载'))).toBe(true)
  })

  it('ignores old stats and content responses after newer refreshes have completed', async () => {
    const oldStats = deferred<typeof stats>()
    const oldContent = deferred<typeof content[]>()
    api.getStats.mockReturnValueOnce(oldStats.promise)
    api.getContents.mockReturnValueOnce(oldContent.promise)
    const wrapper = mountHome()
    await flushPromises()
    await button(wrapper, '刷新统计').trigger('click')
    await button(wrapper, '刷新内容').trigger('click')
    await flushPromises()
    oldStats.resolve({ ...stats, total_contents: 1 })
    oldContent.resolve([])
    await flushPromises()

    expect(wrapper.find('.metric-card strong').text()).toBe('42')
    expect(wrapper.findAll('content-card-stub')).toHaveLength(1)
  })
})
