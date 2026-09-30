import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import Refine from '../src/views/Refine.vue'

const mocks = vi.hoisted(() => ({
  getContent: vi.fn(), getContents: vi.fn(), createRefineJob: vi.fn(), createTitlesJob: vi.fn(),
  createSeoJob: vi.fn(), waitForJobResult: vi.fn(), extractContent: vi.fn(), extractText: vi.fn(),
  error: vi.fn(), warning: vi.fn(), success: vi.fn(), route: { query: {} as Record<string, string> }
}))
vi.mock('../src/api/content', () => mocks)
vi.mock('../src/api/jobs', () => mocks)
vi.mock('vue-router', () => ({ useRoute: () => mocks.route }))
vi.mock('element-plus/es/components/message/index', () => ({ ElMessage: mocks }))

const numberInput = defineComponent({
  props: ['modelValue', 'disabled'], emits: ['update:modelValue'],
  setup(props, { emit }) {
    return () => h('input', {
      type: 'number', value: props.modelValue, disabled: props.disabled,
      onInput: (event: Event) => emit('update:modelValue', Number((event.target as HTMLInputElement).value))
    })
  }
})
const content = (id: number) => ({ id, title: `稿件${id}`, content: `正文${id}`, content_type: 'blog', style: 'professional', status: 'draft' })
const mountRefine = () => shallowMount(Refine, {
  global: {
    renderStubDefaultSlot: true,
    stubs: {
      'el-button': { props: ['disabled'], template: '<button :disabled="disabled"><slot /></button>' },
      'el-input-number': numberInput, 'el-input': true, 'el-icon': true
    }
  }
})
const button = (wrapper: ReturnType<typeof mountRefine>, text: string) => wrapper.findAll('button').find(item => item.text() === text)!

beforeEach(() => {
  mocks.route.query = {}
  mocks.getContents.mockResolvedValue([content(1), content(2)])
  mocks.getContent.mockImplementation(async (id: number) => content(id))
  mocks.createRefineJob.mockResolvedValue({ id: 'job-1', status: 'queued' })
  mocks.createTitlesJob.mockResolvedValue({ id: 'job-1', status: 'queued' })
  mocks.createSeoJob.mockResolvedValue({ id: 'job-1', status: 'queued' })
  mocks.waitForJobResult.mockResolvedValue({ content: '优化后的正文' })
})

describe('refine source selection', () => {
  it.each(['执行改写', '切换风格', '生成标题', '分析 SEO'])('uses the previewed source rather than an unloaded input ID for %s', async label => {
    const wrapper = mountRefine()
    await flushPromises()
    await wrapper.findAll('.recent-card')[0].trigger('click')
    await flushPromises()
    await wrapper.find('input[type="number"]').setValue('99')
    await button(wrapper, label).trigger('click')
    await flushPromises()

    const create = label === '生成标题' ? mocks.createTitlesJob : label === '分析 SEO' ? mocks.createSeoJob : mocks.createRefineJob
    expect(create).toHaveBeenCalledWith(expect.objectContaining({ content_id: 1 }))
  })

  it('does not let an older selection response replace the latest preview', async () => {
    let finishFirst!: (value: ReturnType<typeof content>) => void
    mocks.getContent.mockImplementationOnce(() => new Promise(resolve => { finishFirst = resolve }))
    const wrapper = mountRefine()
    await flushPromises()
    await wrapper.findAll('.recent-card')[0].trigger('click')
    await wrapper.findAll('.recent-card')[1].trigger('click')
    await flushPromises()
    finishFirst(content(1))
    await flushPromises()

    expect(wrapper.find('.source-preview').text()).toContain('正文2')
  })

  it('clears stale source and results when loading a missing content ID', async () => {
    const wrapper = mountRefine()
    await flushPromises()
    await wrapper.findAll('.recent-card')[0].trigger('click')
    await flushPromises()
    mocks.getContent.mockRejectedValueOnce(new Error('内容不存在'))
    await wrapper.find('input[type="number"]').setValue('99')
    await button(wrapper, '加载').trigger('click')
    await flushPromises()
    await button(wrapper, '执行改写').trigger('click')

    expect(wrapper.find('.source-preview').exists()).toBe(false)
    expect(mocks.createRefineJob).not.toHaveBeenCalled()
    expect(mocks.warning).toHaveBeenCalledWith('请先选择内容')
  })

  it('loads the requested content even when the recent library request fails', async () => {
    mocks.route.query = { id: '2' }
    mocks.getContents.mockRejectedValueOnce(new Error('列表暂不可用'))
    const wrapper = mountRefine()
    await flushPromises()

    expect(wrapper.find('.source-preview').text()).toContain('正文2')
    expect(mocks.error).toHaveBeenCalledWith('列表暂不可用')
  })

  it('prevents duplicate jobs and source switches during a running task', async () => {
    mocks.waitForJobResult.mockImplementationOnce(() => new Promise(() => {}))
    const wrapper = mountRefine()
    await flushPromises()
    await wrapper.findAll('.recent-card')[0].trigger('click')
    await flushPromises()
    await button(wrapper, '执行改写').trigger('click')
    await button(wrapper, '执行改写').trigger('click')
    await flushPromises()

    expect(mocks.createRefineJob).toHaveBeenCalledTimes(1)
    expect(wrapper.findAll('.recent-card')[1].attributes('disabled')).toBeDefined()
  })
})
