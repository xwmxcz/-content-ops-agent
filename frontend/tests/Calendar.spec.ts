import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import Calendar from '../src/views/Calendar.vue'
import type { CalendarEvent } from '../src/api/calendar'

const api = vi.hoisted(() => ({ getEvents: vi.fn(), createEvent: vi.fn(), updateEvent: vi.fn(), deleteEvent: vi.fn() }))
const confirm = vi.hoisted(() => vi.fn())
vi.mock('../src/api/calendar', () => api)
vi.mock('element-plus/es/components/message/index', () => ({ ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }))
vi.mock('element-plus/es/components/message-box/index', () => ({ ElMessageBox: { confirm } }))

function key(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}
const today = key(new Date())
const plan: CalendarEvent = { event_id: 31, content_id: 8, platform: 'blog', scheduled_date: today, status: 'planned', content_title: 'Existing draft' }

const CalendarStub = defineComponent({
  props: ['modelValue'], emits: ['update:modelValue'],
  setup(props, { emit }) {
    return () => h('input', {
      'data-test': 'month', value: key(props.modelValue),
      onChange: (event: Event) => emit('update:modelValue', new Date(`${(event.target as HTMLInputElement).value}T12:00:00`))
    })
  }
})
const DateStub = defineComponent({
  props: ['modelValue'], emits: ['update:modelValue'],
  setup(props, { emit }) {
    return () => h('input', { 'data-test': 'schedule-date', value: props.modelValue,
      onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLInputElement).value) })
  }
})

function mountCalendar() {
  return mount(Calendar, { global: { stubs: {
    ElCalendar: CalendarStub, ElDatePicker: DateStub,
    ElDialog: { props: ['modelValue'], template: '<div v-if="modelValue"><slot /><slot name="footer" /></div>' },
    ElForm: { template: '<div><slot /></div>' }, ElFormItem: { template: '<div><slot /></div>' },
    ElInputNumber: true, ElSelect: true, ElOption: true, ElEmpty: true,
    ElButton: { props: ['disabled'], template: '<button :disabled="disabled"><slot /></button>' }
  } } })
}

function button(wrapper: ReturnType<typeof mountCalendar>, text: string) {
  const found = wrapper.findAll('button').find(item => item.text() === text)
  if (!found) throw new Error(`Missing button: ${text}`)
  return found
}

beforeEach(() => {
  api.getEvents.mockResolvedValue([plan])
  api.createEvent.mockResolvedValue({ event_id: 32 })
  api.updateEvent.mockResolvedValue({ event_id: 31 })
  api.deleteEvent.mockResolvedValue(undefined)
  confirm.mockResolvedValue('confirm')
})

describe('Calendar management', () => {
  it('loads the visible month independently of the future summary', async () => {
    const wrapper = mountCalendar()
    await flushPromises()
    await wrapper.get('[data-test="month"]').setValue('2020-01-15')
    await flushPromises()
    expect(api.getEvents).toHaveBeenCalledWith({ start_date: '2019-12-26', end_date: '2020-02-06' })
    expect(api.getEvents).toHaveBeenCalledWith(60)
    wrapper.unmount()
  })

  it('ignores responses from a month the user has left', async () => {
    let resolveOld!: (events: CalendarEvent[]) => void
    api.getEvents.mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve }))
    const wrapper = mountCalendar()
    await wrapper.get('[data-test="month"]').setValue('2020-01-15')
    api.getEvents.mockResolvedValue([{ ...plan, content_title: 'Current month', scheduled_date: '2020-01-15' }])
    await wrapper.get('[data-test="month"]').setValue('2020-01-16')
    await flushPromises()
    resolveOld([{ ...plan, content_title: 'Stale result', scheduled_date: '2020-01-16' }])
    await flushPromises()
    expect(wrapper.text()).not.toContain('Stale result')
    wrapper.unmount()
  })

  it('edits the selected event and navigates to its new month', async () => {
    const wrapper = mountCalendar()
    await flushPromises()
    await button(wrapper, '编辑').trigger('click')
    await wrapper.get('[data-test="schedule-date"]').setValue('2030-05-07')
    await button(wrapper, '保存').trigger('click')
    await flushPromises()
    expect(api.updateEvent).toHaveBeenCalledWith(31, { content_id: 8, platform: 'blog', scheduled_date: '2030-05-07' })
    expect(api.createEvent).not.toHaveBeenCalled()
    expect(api.getEvents).toHaveBeenCalledWith({ start_date: '2030-04-25', end_date: '2030-06-06' })
    expect((wrapper.get('[data-test="month"]').element as HTMLInputElement).value).toBe('2030-05-07')
    wrapper.unmount()
  })

  it('deletes a local plan after confirmation and reloads', async () => {
    const wrapper = mountCalendar()
    await flushPromises()
    api.getEvents.mockResolvedValue([])
    await button(wrapper, '删除').trigger('click')
    await flushPromises()
    expect(confirm).toHaveBeenCalled()
    expect(api.deleteEvent).toHaveBeenCalledWith(31)
    expect(wrapper.find('.agenda-row').exists()).toBe(false)
    wrapper.unmount()
  })

  it('does not delete when confirmation is cancelled', async () => {
    confirm.mockRejectedValue('cancel')
    const wrapper = mountCalendar()
    await flushPromises()
    await button(wrapper, '删除').trigger('click')
    await flushPromises()
    expect(api.deleteEvent).not.toHaveBeenCalled()
    expect(wrapper.find('.agenda-row').exists()).toBe(true)
    wrapper.unmount()
  })

  it('does not offer local edits to an already scheduled platform publication', async () => {
    api.getEvents.mockResolvedValue([{ ...plan, status: 'scheduled' }])
    const wrapper = mountCalendar()
    await flushPromises()
    expect(wrapper.findAll('button').map(item => item.text())).not.toContain('编辑')
    expect(wrapper.findAll('button').map(item => item.text())).not.toContain('删除')
    wrapper.unmount()
  })

  it('shows failed loads as errors instead of an empty synchronized calendar', async () => {
    api.getEvents.mockRejectedValue(new Error('连接失败'))
    const wrapper = mountCalendar()
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('连接失败')
    expect(wrapper.text()).not.toContain('已同步')
    wrapper.unmount()
  })
})
