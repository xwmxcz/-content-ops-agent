import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'
import Studio from '../src/views/Studio.vue'

const jobs = vi.hoisted(() => ({ create: vi.fn(), get: vi.fn(), cancel: vi.fn(), error: vi.fn(), success: vi.fn() }))
vi.mock('../src/api/jobs', async original => ({
  ...await original<typeof import('../src/api/jobs')>(),
  createAgentRunJob: jobs.create, getJob: jobs.get, cancelJob: jobs.cancel
}))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: { topic: '测试主题' } }), useRouter: () => ({ replace: vi.fn(), push: vi.fn() }) }))
vi.mock('element-plus/es/components/message/index', () => ({ ElMessage: { error: jobs.error, success: jobs.success, warning: vi.fn() } }))

const wrappers: ReturnType<typeof shallowMount>[] = []
function mountStudio() {
  const wrapper = shallowMount(Studio, { global: { renderStubDefaultSlot: true, stubs: {
    'el-button': { template: '<button><slot /></button>' }, 'el-input': true, 'el-select': true, 'el-option': true, 'el-icon': true
  } } })
  wrappers.push(wrapper)
  return wrapper
}
function completed(id: string, content: string) {
  return { id, status: 'completed', result: { agent_run: { steps: [], final_content: { content, content_type: 'blog', style: 'professional' } } } }
}
beforeEach(() => {
  jobs.create.mockResolvedValue({ id: 'new-job' })
  jobs.get.mockResolvedValue(completed('new-job', '新流程的最终结果'))
  jobs.cancel.mockResolvedValue({})
})
afterEach(() => wrappers.splice(0).forEach(wrapper => wrapper.unmount()))

describe('Studio workflow attempt isolation', () => {
  it.each(['pending creation', 'late completion', 'late failure'])('keeps the new run intact after stopping an old run with %s', async scenario => {
    let resolveOld!: (value: unknown) => void
    let rejectOld!: (error: Error) => void
    const old = new Promise((resolve, reject) => { resolveOld = resolve; rejectOld = reject })
    if (scenario === 'pending creation') jobs.create.mockReturnValueOnce(old)
    else {
      jobs.create.mockResolvedValueOnce({ id: 'old-job' })
      jobs.get.mockReturnValueOnce(old)
    }
    const wrapper = mountStudio()
    const run = () => wrapper.findAll('button').find(button => button.text() === '运行')!
    await run().trigger('click')
    await flushPromises()
    await wrapper.get('.stop-action').trigger('click')
    await run().trigger('click')
    await flushPromises()
    expect(wrapper.get('.final-body').text()).toBe('新流程的最终结果')
    if (scenario === 'late failure') rejectOld(new Error('旧流程错误'))
    else resolveOld(scenario === 'pending creation' ? { id: 'old-job' } : completed('old-job', '旧流程最终结果'))
    await flushPromises()
    expect(wrapper.get('.final-body').text()).toBe('新流程的最终结果')
    expect(wrapper.text()).not.toContain('旧流程错误')
    expect(jobs.error).not.toHaveBeenCalled()
    expect(jobs.success).toHaveBeenCalledTimes(1)
    if (scenario === 'pending creation') expect(jobs.get.mock.calls.map(call => call[0])).toEqual(['new-job'])
  })
})
