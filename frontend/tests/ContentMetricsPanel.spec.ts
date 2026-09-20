/**
 * Behaviour tests for the panel that records platform numbers.
 *
 * What is worth pinning here: a blank number must never be saved as zero, a
 * re-saved platform must replace its row rather than duplicate it, and a slow
 * response for the previous content must not paint over the current one.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import ContentMetricsPanel from '../src/components/ContentMetricsPanel.vue'
import type { ContentMetrics } from '../src/api/metrics'

const api = vi.hoisted(() => ({
  getContentMetrics: vi.fn(),
  recordContentMetrics: vi.fn()
}))
vi.mock('../src/api/metrics', () => api)
vi.mock('element-plus/es/components/message/index', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() }
}))

// Element Plus is not registered in this suite; this stub keeps v-model working.
const ElInputStub = defineComponent({
  props: { modelValue: { type: [String, Number], default: '' } },
  emits: ['update:modelValue'],
  setup(props, { emit }) {
    return () =>
      h('input', {
        value: props.modelValue,
        onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLInputElement).value)
      })
  }
})

function row(overrides: Partial<ContentMetrics> = {}): ContentMetrics {
  return {
    id: 1,
    content_id: 7,
    platform: 'xiaohongshu',
    views: 18400,
    likes: 1240,
    comments: 96,
    shares: 210,
    engagement_rate: 0.084,
    recorded_at: '2026-09-19T10:00:00',
    ...overrides
  }
}

function mountPanel(props: Record<string, unknown> = {}) {
  return mount(ContentMetricsPanel, {
    props: { contentId: 7, defaultPlatform: 'xiaohongshu', ...props },
    global: {
      stubs: {
        'el-input': ElInputStub,
        'el-button': { template: '<button type="submit"><slot /></button>' }
      }
    }
  })
}

async function fill(wrapper: ReturnType<typeof mountPanel>, values: string[]) {
  const inputs = wrapper.findAll('input')
  for (const [index, value] of values.entries()) await inputs[index].setValue(value)
}

beforeEach(() => {
  api.getContentMetrics.mockResolvedValue([])
  api.recordContentMetrics.mockImplementation(async (contentId: number, payload: Partial<ContentMetrics>) =>
    row({ content_id: contentId, ...payload })
  )
})

describe('ContentMetricsPanel', () => {
  it('lists what is on file with a readable engagement rate', async () => {
    api.getContentMetrics.mockResolvedValue([row()])
    const wrapper = mountPanel()
    await flushPromises()

    expect(wrapper.text()).toContain('已记录 1 个平台')
    expect(wrapper.text()).toContain('18,400')
    expect(wrapper.text()).toContain('8.4%')
  })

  it('starts from the content type as the platform and does not greet the user with an error', async () => {
    const wrapper = mountPanel()
    await flushPromises()

    expect((wrapper.findAll('input')[0].element as HTMLInputElement).value).toBe('xiaohongshu')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })

  it('refuses to save a blank view count as zero', async () => {
    const wrapper = mountPanel()
    await flushPromises()

    await wrapper.find('form').trigger('submit')

    expect(api.recordContentMetrics).not.toHaveBeenCalled()
    expect(wrapper.find('[role="alert"]').text()).toContain('浏览')
  })

  it.each([['-5'], ['1.5'], ['12abc'], ['3000000000']])('rejects %s as a count', async value => {
    const wrapper = mountPanel()
    await flushPromises()
    await fill(wrapper, ['xiaohongshu', value])

    await wrapper.find('form').trigger('submit')

    expect(api.recordContentMetrics).not.toHaveBeenCalled()
  })

  it('sends normalized numbers and shows the saved row', async () => {
    const wrapper = mountPanel()
    await flushPromises()
    await fill(wrapper, [' WeChat ', '900', '45', '6', '3'])

    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(api.recordContentMetrics).toHaveBeenCalledWith(7, {
      platform: 'wechat',
      views: 900,
      likes: 45,
      comments: 6,
      shares: 3
    })
    expect(wrapper.text()).toContain('wechat')
    expect(wrapper.text()).toContain('900')
  })

  it('replaces a platform row on re-save instead of listing it twice', async () => {
    api.getContentMetrics.mockResolvedValue([row({ views: 100 })])
    const wrapper = mountPanel()
    await flushPromises()

    await wrapper.find('.metrics-platform').trigger('click')
    await fill(wrapper, ['xiaohongshu', '250'])
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(wrapper.findAll('.metrics-row')).toHaveLength(1)
    expect(wrapper.find('.metrics-row').text()).toContain('250')
  })

  it('reloads in place after an import, keeping the panel open and a half-typed form intact', async () => {
    const wrapper = mountPanel({ refreshKey: 0 })
    await flushPromises()
    ;(wrapper.find('details').element as HTMLDetailsElement).open = true
    await fill(wrapper, ['wechat', '77'])
    api.getContentMetrics.mockResolvedValue([row({ platform: 'douyin', views: 3200 })])

    await wrapper.setProps({ refreshKey: 1 })
    await flushPromises()

    expect(wrapper.text()).toContain('douyin')
    expect((wrapper.find('details').element as HTMLDetailsElement).open).toBe(true)
    expect((wrapper.findAll('input')[1].element as HTMLInputElement).value).toBe('77')
  })

  it('clears the form when the user moves to different content', async () => {
    const wrapper = mountPanel()
    await flushPromises()
    await fill(wrapper, ['wechat', '77'])

    await wrapper.setProps({ contentId: 8, defaultPlatform: 'blog' })
    await flushPromises()

    const values = wrapper.findAll('input').map(input => (input.element as HTMLInputElement).value)
    expect(values.slice(0, 2)).toEqual(['blog', ''])
  })

  it('ignores a late response for content the user has already left', async () => {
    let resolveFirst: (rows: ContentMetrics[]) => void = () => {}
    api.getContentMetrics
      .mockImplementationOnce(() => new Promise<ContentMetrics[]>(resolve => (resolveFirst = resolve)))
      .mockResolvedValueOnce([row({ id: 2, content_id: 8, platform: 'blog', views: 5 })])
    const wrapper = mountPanel()

    await wrapper.setProps({ contentId: 8 })
    await flushPromises()
    resolveFirst([row({ platform: 'stale-platform' })])
    await flushPromises()

    expect(wrapper.text()).toContain('blog')
    expect(wrapper.text()).not.toContain('stale-platform')
  })
})
