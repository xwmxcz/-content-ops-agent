import { queryTestPlugin, disposeQueryTests } from './queryTestUtils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import History from '../src/views/History.vue'
import ContentEditorDialog from '../src/components/ContentEditorDialog.vue'
import type { ContentItem } from '../src/api/content'
import { setAuthToken } from '../src/api'

const mocks = vi.hoisted(() => ({
  getContents: vi.fn(), getContent: vi.fn(), archiveContent: vi.fn(), deleteContentLocal: vi.fn(), restoreContent: vi.fn(),
  getContentMedia: vi.fn(), uploadMedia: vi.fn(), deleteMedia: vi.fn(),
  getContentPublications: vi.fn(), getXiaohongshuLoginStatus: vi.fn(),
  publishToXiaohongshu: vi.fn(), scheduleXiaohongshuPublication: vi.fn(),
  error: vi.fn(), success: vi.fn(), warning: vi.fn(), downloadContent: vi.fn()
}))
vi.mock('../src/api/content', () => mocks)
vi.mock('../src/api/media', () => mocks)
vi.mock('../src/api/publish', () => mocks)
vi.mock('../src/utils/contentExport', () => mocks)
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('element-plus/es/components/message/index', () => ({ ElMessage: mocks }))

function content(id: number): ContentItem {
  return { id, title: `稿件${id}`, content: `正文${id}`, content_type: 'blog', style: 'professional', status: 'draft' }
}
function asset(id: number) {
  return { id, content_id: id, media_type: 'image', file_name: `图片${id}`, file_url: `/image-${id}.png` }
}
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}
const inputStub = defineComponent({
  props: ['modelValue'], emits: ['update:modelValue'],
  setup(props, { emit }) {
    return () => h('input', {
      value: props.modelValue,
      onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLInputElement).value)
    })
  }
})
const wrappers: ReturnType<typeof shallowMount>[] = []
function mountHistory() {
  const wrapper = shallowMount(History, {
    global: {
      plugins: [queryTestPlugin()],
      renderStubDefaultSlot: true,
      stubs: {
        'el-button': { template: '<button><slot /></button>' },
        'el-input': inputStub, 'el-select': true, 'el-option': true, 'el-icon': true, 'router-link': true
      }
    }
  })
  wrappers.push(wrapper)
  return wrapper
}

afterEach(() => {
  wrappers.splice(0).forEach(wrapper => wrapper.unmount())
  vi.useRealTimers()
})

beforeEach(() => {
  mocks.getContents.mockResolvedValue([content(1), content(2)])
  mocks.getContent.mockImplementation(async (id: number) => content(id))
  mocks.getContentMedia.mockResolvedValue([])
  mocks.getContentPublications.mockResolvedValue([])
  mocks.getXiaohongshuLoginStatus.mockResolvedValue({ connected: true })
  mocks.uploadMedia.mockResolvedValue(asset(1))
})

describe('history content isolation', () => {
  it('opens the editor with full content and reflects saved text in the detail', async () => {
    const wrapper = mountHistory()
    await flushPromises()
    await wrapper.findAll('.library-card')[0].trigger('click')
    await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '手动编辑')!.trigger('click')
    const editor = wrapper.findComponent(ContentEditorDialog)
    expect(editor.props('open')).toBe(true)
    expect(editor.props('content')).toEqual(content(1))
    editor.vm.$emit('saved', { ...content(1), title: '修改后标题', content: '修改后全文' })
    await flushPromises()
    expect(wrapper.get('.content-preview').text()).toBe('修改后全文')
    expect(wrapper.get('.detail-section h2').text()).toBe('修改后标题')
  })

  it('restores an archived item and exports its full detail rather than its preview', async () => {
    const full = { ...content(1), content: '完整正文'.repeat(300), status: 'archived' }
    mocks.getContent.mockResolvedValueOnce(full)
    mocks.restoreContent.mockResolvedValueOnce({ ...full, status: 'draft' })
    const wrapper = mountHistory()
    await flushPromises()
    await wrapper.findAll('.library-card')[0].trigger('click')
    await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '恢复为草稿')!.trigger('click')
    await flushPromises()
    expect(mocks.restoreContent).toHaveBeenCalledExactlyOnceWith(1)
    expect(wrapper.findAll('button').some(button => button.text() === '恢复为草稿')).toBe(false)
    await wrapper.findAll('button').find(button => button.text() === '导出 Markdown')!.trigger('click')
    expect(mocks.downloadContent).toHaveBeenCalledWith({ ...full, status: 'draft' })
  })

  it('reuses fresh details when returning to an already visited content', async () => {
    const wrapper = mountHistory()
    await flushPromises()
    for (const index of [0, 1, 0]) {
      await wrapper.findAll('.library-card')[index].trigger('click')
      await flushPromises()
    }
    expect(mocks.getContent.mock.calls.map(call => call[0])).toEqual([1, 2])
    expect(wrapper.get('.content-preview').text()).toBe('正文1')
  })

  it('discards selected content and stops a multi-file upload when the account changes', async () => {
    const upload = deferred<ReturnType<typeof asset>>()
    mocks.uploadMedia.mockImplementationOnce(() => upload.promise)
    const wrapper = mountHistory()
    await flushPromises()
    await wrapper.findAll('.library-card')[0].trigger('click')
    await flushPromises()
    const input = wrapper.find('input[accept="image/*"]')
    Object.defineProperty(input.element, 'files', { value: [new File(['a'], 'a.png'), new File(['b'], 'b.png')] })
    await input.trigger('change')
    mocks.getContents.mockResolvedValue([])
    setAuthToken('new-account')
    upload.resolve(asset(1))
    await flushPromises()
    expect(mocks.uploadMedia).toHaveBeenCalledTimes(1)
    expect(wrapper.find('.content-preview').exists()).toBe(false)
    expect(wrapper.findAll('.library-card')).toHaveLength(0)
  })

  it('keeps loaded pages on a next-page failure and retries the same offset without duplicates', async () => {
    mocks.getContents.mockResolvedValueOnce(Array.from({ length: 30 }, (_, index) => content(index + 1)))
    const wrapper = mountHistory()
    await flushPromises()
    mocks.getContents.mockRejectedValueOnce(new Error('暂时离线')).mockResolvedValueOnce([content(30), content(31)])
    const more = () => wrapper.findAll('button').find(button => button.text() === '加载更多')!
    await more().trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.library-card')).toHaveLength(30)
    expect(wrapper.get('[role="alert"]').text()).toContain('暂时离线')
    await more().trigger('click')
    await flushPromises()
    expect(mocks.getContents.mock.calls.map(call => call[0].offset)).toEqual([0, 30, 30])
    expect(wrapper.findAll('.library-card')).toHaveLength(31)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })

  it('keeps the most recently selected content when detail responses arrive out of order', async () => {
    const first = deferred<ContentItem>()
    mocks.getContent.mockImplementationOnce(() => first.promise)
    const wrapper = mountHistory()
    await flushPromises()
    await wrapper.findAll('.library-card')[0].trigger('click')
    await wrapper.findAll('.library-card')[1].trigger('click')
    await flushPromises()
    first.resolve(content(1))
    await flushPromises()

    expect(wrapper.find('.detail-section h2').text()).toBe('稿件2')
    expect(wrapper.find('.content-preview').text()).toBe('正文2')
  })

  it('clears previous media immediately and ignores its late response', async () => {
    const firstMedia = deferred<ReturnType<typeof asset>[]>()
    mocks.getContentMedia.mockImplementationOnce(() => firstMedia.promise).mockResolvedValueOnce([asset(2)])
    const wrapper = mountHistory()
    await flushPromises()
    await wrapper.findAll('.library-card')[0].trigger('click')
    await flushPromises()
    await wrapper.findAll('.library-card')[1].trigger('click')
    await flushPromises()
    firstMedia.resolve([asset(1)])
    await flushPromises()

    expect(wrapper.findAll('.media-card')).toHaveLength(1)
    expect(wrapper.find('.media-card').text()).toContain('图片2')
    expect(wrapper.find('.media-card').text()).not.toContain('图片1')
  })

  it('uploads every selected file to the original content even if the user changes selection', async () => {
    const upload = deferred<ReturnType<typeof asset>>()
    mocks.uploadMedia.mockImplementationOnce(() => upload.promise)
    const wrapper = mountHistory()
    await flushPromises()
    await wrapper.findAll('.library-card')[0].trigger('click')
    await flushPromises()
    const input = wrapper.find('input[accept="image/*"]')
    const files = [new File(['a'], 'a.png'), new File(['b'], 'b.png')]
    Object.defineProperty(input.element, 'files', { value: files })
    await input.trigger('change')
    await wrapper.findAll('.library-card')[1].trigger('click')
    await flushPromises()
    upload.resolve(asset(1))
    await flushPromises()

    expect(mocks.uploadMedia.mock.calls.map(call => call[0])).toEqual([1, 1])
    expect(wrapper.find('.detail-section h2').text()).toBe('稿件2')
    expect(wrapper.findAll('.media-card')).toHaveLength(0)
  })

  it('reports a failed detail request and removes the previous actionable content', async () => {
    const wrapper = mountHistory()
    await flushPromises()
    await wrapper.findAll('.library-card')[0].trigger('click')
    await flushPromises()
    mocks.getContent.mockRejectedValueOnce(new Error('内容不存在'))
    await wrapper.findAll('.library-card')[1].trigger('click')
    await flushPromises()

    expect(mocks.error).toHaveBeenCalledWith('内容不存在')
    expect(wrapper.find('.detail-actions').exists()).toBe(false)
  })

  it('keeps the latest filter result when list responses arrive out of order', async () => {
    const oldList = deferred<ContentItem[]>()
    const wrapper = mountHistory()
    await flushPromises()
    mocks.getContents.mockImplementationOnce(() => oldList.promise).mockResolvedValueOnce([content(2)])
    const filter = wrapper.findAll('button').find(button => button.text() === '筛选')!
    await filter.trigger('click')
    await filter.trigger('click')
    await flushPromises()
    oldList.resolve([content(1)])
    await flushPromises()

    expect(wrapper.findAll('.library-card')).toHaveLength(1)
    expect(wrapper.find('.library-card').attributes('aria-label')).toBe('查看内容 稿件2')
  })

  it('loads beyond the first 100 contents using server pagination', async () => {
    const allContents = Array.from({ length: 101 }, (_, index) => content(index + 1))
    mocks.getContents.mockImplementation(async ({ offset, limit }) => allContents.slice(offset, offset + limit))
    const wrapper = mountHistory()
    await flushPromises()
    for (let page = 0; page < 3; page++) {
      await wrapper.findAll('button').find(button => button.text() === '加载更多')!.trigger('click')
      await flushPromises()
    }

    expect(wrapper.findAll('.library-card')).toHaveLength(101)
    expect(mocks.getContents.mock.calls.map(call => call[0].offset)).toEqual([0, 30, 60, 90])
    expect(wrapper.find('.list-pagination').exists()).toBe(false)
  })

  it('debounces server searches and keeps matches whose keyword is outside the preview', async () => {
    vi.useFakeTimers()
    const wrapper = mountHistory()
    await flushPromises()
    mocks.getContents.mockResolvedValue([content(101)])
    const search = wrapper.find('input[placeholder="搜索全部内容的标题或正文"]')
    await search.setValue('正')
    await vi.advanceTimersByTimeAsync(150)
    await search.setValue('正文尾部关键词')
    await vi.advanceTimersByTimeAsync(299)
    expect(mocks.getContents).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1)
    await flushPromises()

    expect(mocks.getContents).toHaveBeenLastCalledWith(expect.objectContaining({ q: '正文尾部关键词', offset: 0, limit: 30 }), expect.any(AbortSignal))
    expect(wrapper.findAll('.library-card')).toHaveLength(1)
    expect(wrapper.find('.library-card').attributes('aria-label')).toBe('查看内容 稿件101')
  })

  it('discards a previous page response after the search query changes', async () => {
    vi.useFakeTimers()
    mocks.getContents.mockResolvedValueOnce(Array.from({ length: 30 }, (_, index) => content(index + 1)))
    const oldPage = deferred<ContentItem[]>()
    const wrapper = mountHistory()
    await flushPromises()
    mocks.getContents.mockImplementationOnce(() => oldPage.promise).mockResolvedValueOnce([content(101)])
    await wrapper.findAll('button').find(button => button.text() === '加载更多')!.trigger('click')
    await wrapper.find('input[placeholder="搜索全部内容的标题或正文"]').setValue('关键词')
    await vi.advanceTimersByTimeAsync(300)
    await flushPromises()
    oldPage.resolve([content(31)])
    await flushPromises()

    expect(wrapper.findAll('.library-card')).toHaveLength(1)
    expect(wrapper.find('.library-card').attributes('aria-label')).toBe('查看内容 稿件101')
  })

  it('shows a failed search explicitly instead of an empty result message', async () => {
    vi.useFakeTimers()
    mocks.getContents.mockResolvedValueOnce([])
    const wrapper = mountHistory()
    await flushPromises()
    mocks.getContents.mockRejectedValueOnce(new Error('搜索服务暂不可用'))
    await wrapper.find('input[placeholder="搜索全部内容的标题或正文"]').setValue('关键词')
    await vi.advanceTimersByTimeAsync(300)
    await flushPromises()

    expect(wrapper.find('[role="alert"]').text()).toBe('搜索服务暂不可用')
    expect(wrapper.find('[description="暂无匹配内容"]').exists()).toBe(false)
  })
})

afterEach(disposeQueryTests)
