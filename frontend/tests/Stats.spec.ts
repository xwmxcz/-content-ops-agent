import { queryTestPlugin, disposeQueryTests } from './queryTestUtils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import Stats from '../src/views/Stats.vue'
import type { PerformanceStats, PerformanceTotals } from '../src/api/stats'
import { setAuthToken } from '../src/api'

const api = vi.hoisted(() => ({ getStats: vi.fn(), getPerformanceStats: vi.fn() }))
vi.mock('../src/api/stats', () => api)
vi.mock('vue-echarts', () => ({ default: { name: 'VChart', props: ['option'], template: '<div class="test-chart" />' } }))

function totals(override: Partial<PerformanceTotals> = {}): PerformanceTotals {
  return { metric_rows: 1, views: 2000, likes: 100, comments: 40, shares: 60, interactions: 200, engagement_rate: 0.1, ...override }
}

function performance(override: Partial<PerformanceStats> = {}): PerformanceStats {
  return {
    window_days: 30, window_start: '2026-08-31', window_end: '2026-09-29', platform: null,
    available_platforms: ['blog', 'wechat'], total_contents: 2, measured_contents: 1, missing_contents: 1,
    last_recorded_at: '2026-09-29T10:00:00', totals: totals(),
    by_platform: [{ platform: 'blog', ...totals() }],
    by_creation_date: [{ date: '2026-09-29', total_contents: 2, measured_contents: 1, ...totals() }],
    top_contents: [{ content_id: 8, title: 'Winning content', platform: 'blog', ...totals() }],
    ...override
  }
}

const wrappers: ReturnType<typeof mount>[] = []
function mountStats() {
  const wrapper = mount(Stats, { global: { plugins: [queryTestPlugin()], stubs: {
    ElButton: { template: '<button><slot /></button>' },
    ElEmpty: { props: ['description'], template: '<div>{{ description }}</div>' },
    RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' }
  } } })
  wrappers.push(wrapper)
  return wrapper
}

afterEach(() => wrappers.splice(0).forEach(wrapper => wrapper.unmount()))

beforeEach(() => {
  api.getStats.mockResolvedValue({ total_contents: 2, by_type: { blog: 2 }, by_status: { draft: 2 } })
  api.getPerformanceStats.mockResolvedValue(performance())
})

describe('Stats performance data', () => {
  it('reuses the matching fresh filter cache without fetching or showing another filter response', async () => {
    const wrapper = mountStats()
    await flushPromises()
    api.getPerformanceStats.mockResolvedValueOnce(performance({ top_contents: [{ content_id: 9, title: 'Seven days', platform: 'blog', ...totals() }] }))
    await wrapper.get('#performance-days').setValue('7')
    await flushPromises()
    expect(wrapper.text()).toContain('Seven days')
    await wrapper.get('#performance-days').setValue('30')
    await flushPromises()
    expect(wrapper.text()).toContain('Winning content')
    expect(wrapper.text()).not.toContain('Seven days')
    expect(api.getPerformanceStats).toHaveBeenCalledTimes(2)
  })

  it('clears account-specific totals, rankings and platform choices before a new account loads', async () => {
    api.getPerformanceStats.mockResolvedValueOnce(performance({ available_platforms: ['private-platform'] }))
    const wrapper = mountStats()
    await flushPromises()
    api.getStats.mockImplementationOnce(() => new Promise(() => {}))
    api.getPerformanceStats.mockImplementationOnce(() => new Promise(() => {}))
    setAuthToken('another-account')
    await flushPromises()
    expect(wrapper.findAll('.summary-card > strong').map(item => item.text())).toEqual(['—', '—', '—', '—'])
    expect(wrapper.text()).not.toContain('Winning content')
    expect(wrapper.get('#performance-platform').text()).not.toContain('private-platform')
  })

  it('shows real recorded totals, coverage and ranking with a clear cumulative-value basis', async () => {
    const wrapper = mountStats()
    await flushPromises()
    const panel = wrapper.get('[aria-label="内容效果分析"]')
    expect(api.getPerformanceStats).toHaveBeenCalledWith({ days: 30, platform: undefined }, expect.any(AbortSignal))
    expect(panel.text()).toContain('2,000')
    expect(panel.text()).toContain('10.0%')
    expect(panel.text()).toContain('50%')
    expect(panel.text()).toContain('1 篇未录入')
    expect(panel.text()).toContain('Winning content')
    expect(panel.text()).toContain('不是期间新增量')
    expect(panel.text()).toContain('不代表当天新增浏览')
    wrapper.unmount()
  })

  it('sends both creation-window and platform filters', async () => {
    const wrapper = mountStats()
    await flushPromises()
    await wrapper.get('#performance-days').setValue('7')
    await flushPromises()
    await wrapper.get('#performance-platform').setValue('wechat')
    await flushPromises()
    expect(api.getPerformanceStats).toHaveBeenLastCalledWith({ days: 7, platform: 'wechat' }, expect.any(AbortSignal))
    wrapper.unmount()
  })

  it('distinguishes missing readings from recorded zero views and an undefined rate', async () => {
    const zero = totals({ views: 0, likes: 0, comments: 0, shares: 0, interactions: 0, engagement_rate: null })
    api.getPerformanceStats.mockResolvedValue(performance({ totals: zero, by_platform: [{ platform: 'blog', ...zero }], top_contents: [] }))
    const wrapper = mountStats()
    await flushPromises()
    const panel = wrapper.get('[aria-label="内容效果分析"]')
    expect(panel.text()).toContain('整体互动率—')
    expect(panel.find('.performance-summary').exists()).toBe(true)
    expect(panel.text()).not.toContain('尚无效果读数')
    wrapper.unmount()
  })

  it('offers a data-entry link for missing metrics rather than displaying zero performance', async () => {
    api.getPerformanceStats.mockResolvedValue(performance({ measured_contents: 0, missing_contents: 2, totals: totals({ metric_rows: 0 }), by_platform: [], top_contents: [] }))
    const wrapper = mountStats()
    await flushPromises()
    const panel = wrapper.get('[aria-label="内容效果分析"]')
    expect(panel.text()).toContain('尚无效果读数')
    expect(panel.get('a').attributes('href')).toBe('/history')
    expect(panel.find('.performance-summary').exists()).toBe(false)
    wrapper.unmount()
  })

  it('preserves content statistics and offers retry when only performance loading fails', async () => {
    api.getPerformanceStats.mockRejectedValueOnce(new Error('offline'))
    const wrapper = mountStats()
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('效果数据加载失败')
    expect(wrapper.get('[aria-label="统计摘要"]').text()).toContain('总内容2')
    await wrapper.get('[role="alert"] button').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Winning content')
    wrapper.unmount()
  })

  it('does not let an older filter response replace the latest results', async () => {
    let resolveOld!: (value: PerformanceStats) => void
    api.getPerformanceStats.mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve }))
    const wrapper = mountStats()
    await wrapper.get('#performance-days').setValue('7')
    await flushPromises()
    resolveOld(performance({ top_contents: [{ content_id: 999, title: 'Outdated filter', platform: 'blog', ...totals() }] }))
    await flushPromises()
    expect(wrapper.text()).toContain('Winning content')
    expect(wrapper.text()).not.toContain('Outdated filter')
    wrapper.unmount()
  })

  it('keeps full long platform values and large readings available without abbreviating the data', async () => {
    const platform = 'p'.repeat(50)
    api.getPerformanceStats.mockResolvedValue(performance({
      available_platforms: [platform], totals: totals({ views: 2_000_000_000 })
    }))
    const wrapper = mountStats()
    await flushPromises()
    await wrapper.get('#performance-platform').setValue(platform)
    await flushPromises()
    expect(wrapper.get('#performance-platform').attributes('title')).toBe(platform)
    expect(api.getPerformanceStats).toHaveBeenLastCalledWith({ days: 30, platform }, expect.any(AbortSignal))
    expect(wrapper.get('.performance-summary strong').text()).toBe('2,000,000,000')
    wrapper.unmount()
  })
})

describe('Stats content summary availability', () => {
  it('keeps unresolved statistics unknown, then displays a verified empty library as zero', async () => {
    let resolveCounts!: (value: { total_contents: number; by_type: {}; by_status: {} }) => void
    api.getStats.mockImplementationOnce(() => new Promise(resolve => { resolveCounts = resolve }))
    const wrapper = mountStats()
    await flushPromises()
    expect(wrapper.findAll('.summary-card > strong').map(item => item.text())).toEqual(['—', '—', '—', '—'])
    expect(wrapper.get('.analytics-grid').text()).not.toContain('暂无内容类型数据')
    expect(wrapper.get('.analytics-grid').text()).not.toContain('暂无内容状态数据')
    expect(wrapper.get('.insight-band').text()).toContain('等待统计数据')

    resolveCounts({ total_contents: 0, by_type: {}, by_status: {} })
    await flushPromises()
    expect(wrapper.findAll('.summary-card > strong').map(item => item.text())).toEqual(['0', '0', '0', '0%'])
    expect(wrapper.get('.analytics-grid').text()).toContain('暂无内容类型数据')
    wrapper.unmount()
  })

  it('reports an initial failure without implying there is no content, and retries counts independently', async () => {
    api.getStats.mockRejectedValueOnce(new Error('offline'))
    const wrapper = mountStats()
    await flushPromises()
    expect(wrapper.findAll('.summary-card > strong').map(item => item.text())).toEqual(['—', '—', '—', '—'])
    expect(wrapper.get('[role="alert"]').text()).toContain('内容统计加载失败')
    expect(wrapper.get('.analytics-grid').text()).toContain('尚未加载')
    expect(wrapper.get('.analytics-grid').text()).not.toContain('暂无内容')
    expect(wrapper.get('[aria-label="内容效果分析"]').text()).toContain('Winning content')

    await wrapper.get('[role="alert"] button').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.summary-card > strong')[0].text()).toBe('2')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(api.getPerformanceStats).toHaveBeenCalledOnce()
    expect(api.getStats).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('preserves loaded statistics and marks them as possibly outdated after refresh failure', async () => {
    const wrapper = mountStats()
    await flushPromises()
    api.getStats.mockRejectedValueOnce(new Error('offline'))
    await wrapper.get('.hero-actions button').trigger('click')
    await flushPromises()

    expect(wrapper.findAll('.summary-card > strong').map(item => item.text())).toEqual(['2', '1', '1', '100%'])
    expect(wrapper.get('[role="alert"]').text()).toContain('上次成功加载的数据，可能已过期')
    expect(wrapper.get('.distribution-list').text()).toContain('2 篇')
    wrapper.unmount()
  })
})

afterEach(disposeQueryTests)
