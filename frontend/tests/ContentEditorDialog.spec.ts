import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import ContentEditorDialog from '../src/components/ContentEditorDialog.vue'
import { activateWorkspaceSession, clearWorkspaceSession } from '../src/workspaceSession'

const mocks = vi.hoisted(() => ({ editContent: vi.fn(), getContent: vi.fn(), confirm: vi.fn(), success: vi.fn(), leave: vi.fn() }))
vi.mock('../src/api/content', () => mocks)
vi.mock('element-plus/es/components/message/index', () => ({ ElMessage: mocks }))
vi.mock('element-plus/es/components/message-box/index', () => ({ ElMessageBox: mocks }))
vi.mock('vue-router', () => ({ onBeforeRouteLeave: mocks.leave }))
const content = { id: 1, title: '原稿', content: '原正文', tags: ['品牌'], content_type: 'blog', style: 'casual', status: 'draft', updated_at: '2026-10-14T10:00:00' }
const input = defineComponent({
  props: ['modelValue', 'disabled'], emits: ['update:modelValue'],
  setup(props, { emit }) {
    return () => h('textarea', { value: props.modelValue, disabled: props.disabled,
      onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLTextAreaElement).value) })
  }
})
const wrappers: ReturnType<typeof shallowMount>[] = []
function mountEditor() {
  const wrapper = shallowMount(ContentEditorDialog, { props: { open: true, content }, global: { stubs: {
    'el-dialog': { template: '<div><slot /><slot name="footer" /></div>' },
    'el-button': { props: ['disabled'], template: '<button :disabled="disabled"><slot /></button>' },
    'el-input': input
  } } })
  wrappers.push(wrapper)
  return wrapper
}
const button = (wrapper: ReturnType<typeof mountEditor>, text: string) => wrapper.findAll('button').find(item => item.text() === text)!
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}
beforeEach(() => {
  clearWorkspaceSession(); activateWorkspaceSession()
  mocks.confirm.mockResolvedValue('confirm')
  mocks.editContent.mockResolvedValue({ ...content, content: '新正文' })
  mocks.getContent.mockResolvedValue({ ...content, content: '其他编辑器已保存的正文', updated_at: '2026-10-14T11:00:00' })
})
afterEach(() => wrappers.splice(0).forEach(wrapper => wrapper.unmount()))

describe('manual content editing', () => {
  it('sends the loaded revision token and guards repeat submissions', async () => {
    const response = deferred<typeof content>()
    mocks.editContent.mockReturnValueOnce(response.promise)
    const wrapper = mountEditor()
    await wrapper.get('[aria-label="编辑正文"]').setValue('新正文')
    await wrapper.get('[aria-label="编辑标签"]').setValue('品牌，品牌, 新标签')
    await button(wrapper, '保存修改').trigger('click')
    await button(wrapper, '保存修改').trigger('click')
    expect(mocks.editContent).toHaveBeenCalledExactlyOnceWith(1, {
      title: '原稿', content: '新正文', tags: ['品牌', '新标签'], expected_updated_at: content.updated_at
    })
    response.resolve({ ...content, content: '新正文' })
    await flushPromises()
    expect(wrapper.emitted('saved')).toHaveLength(1)
    expect(wrapper.emitted('update:open')).toEqual([[false]])
  })

  it('keeps input after a conflict and requires a confirmed reload', async () => {
    mocks.editContent.mockRejectedValueOnce(Object.assign(new Error('内容已更新'), { status: 409 }))
    const wrapper = mountEditor()
    await wrapper.get('[aria-label="编辑正文"]').setValue('未保存的修改')
    await button(wrapper, '保存修改').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toBe('内容已更新')
    expect((wrapper.get('[aria-label="编辑正文"]').element as HTMLTextAreaElement).value).toBe('未保存的修改')
    expect(button(wrapper, '保存修改').attributes('disabled')).toBeDefined()
    mocks.confirm.mockRejectedValueOnce('cancel')
    await button(wrapper, '重新加载最新内容').trigger('click')
    await flushPromises()
    expect(mocks.getContent).not.toHaveBeenCalled()
    await button(wrapper, '重新加载最新内容').trigger('click')
    await flushPromises()
    expect((wrapper.get('[aria-label="编辑正文"]').element as HTMLTextAreaElement).value).toBe('其他编辑器已保存的正文')
  })

  it('retains text on network failure and allows a retry', async () => {
    mocks.editContent.mockRejectedValueOnce(new Error('网络连接失败'))
    const wrapper = mountEditor()
    await wrapper.get('[aria-label="编辑正文"]').setValue('新正文')
    await button(wrapper, '保存修改').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('saved')).toBeUndefined()
    expect(button(wrapper, '保存修改').attributes('disabled')).toBeUndefined()
    await button(wrapper, '保存修改').trigger('click')
    await flushPromises()
    expect(mocks.editContent).toHaveBeenCalledTimes(2)
    expect(wrapper.emitted('saved')).toHaveLength(1)
  })

  it('does not publish a late saved response into another workspace', async () => {
    const response = deferred<typeof content>()
    mocks.editContent.mockReturnValueOnce(response.promise)
    const wrapper = mountEditor()
    await wrapper.get('[aria-label="编辑正文"]').setValue('新正文')
    await button(wrapper, '保存修改').trigger('click')
    clearWorkspaceSession(); activateWorkspaceSession()
    response.resolve(content)
    await flushPromises()
    expect(wrapper.emitted('saved')).toBeUndefined()
    expect(mocks.success).not.toHaveBeenCalled()
  })

  it('prevents accidental navigation or closing with unsaved text', async () => {
    const wrapper = mountEditor()
    await wrapper.get('[aria-label="编辑正文"]').setValue('尚未保存')
    mocks.confirm.mockRejectedValueOnce('cancel')
    expect(await mocks.leave.mock.calls[0][0]()).toBe(false)
    mocks.confirm.mockRejectedValueOnce('cancel')
    await button(wrapper, '取消').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('update:open')).toBeUndefined()
    const unload = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(unload)
    expect(unload.defaultPrevented).toBe(true)
  })

  it('rejects blank text before sending any request', async () => {
    const wrapper = mountEditor()
    await wrapper.get('[aria-label="编辑正文"]').setValue(' \n ')
    await button(wrapper, '保存修改').trigger('click')
    expect(mocks.editContent).not.toHaveBeenCalled()
  })
})
