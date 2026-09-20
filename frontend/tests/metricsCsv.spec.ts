/**
 * The CSV parser is the only validation a spreadsheet gets before it becomes
 * analytics data, so every way a real export goes wrong has to surface as a
 * line-numbered message rather than as a silently wrong number.
 */
import { describe, expect, it } from 'vitest'
import { METRICS_CSV_TEMPLATE, METRICS_IMPORT_MAX_ROWS, parseMetricsCsv } from '../src/utils/metricsCsv'

describe('parseMetricsCsv', () => {
  it('parses the template it offers the user', () => {
    expect(parseMetricsCsv(METRICS_CSV_TEMPLATE)).toEqual({
      rows: [{ content_id: 12, platform: 'xiaohongshu', views: 18400, likes: 1240, comments: 96, shares: 210 }],
      errors: []
    })
  })

  it('reads columns by header name, in any order, defaulting the optional ones to zero', () => {
    const { rows, errors } = parseMetricsCsv('views,platform,content_id\n300,WeChat,7')

    expect(errors).toEqual([])
    expect(rows).toEqual([{ content_id: 7, platform: 'wechat', views: 300, likes: 0, comments: 0, shares: 0 }])
  })

  it('accepts cells pasted from a spreadsheet: tabs, a BOM, quotes, CRLF and blank lines', () => {
    const pasted = '﻿content_id\tplatform\tviews\tlikes\r\n\r\n"3"\t"blog"\t1200\t40\r\n'

    expect(parseMetricsCsv(pasted).rows).toEqual([
      { content_id: 3, platform: 'blog', views: 1200, likes: 40, comments: 0, shares: 0 }
    ])
  })

  it('names the missing columns instead of guessing at a headerless sheet', () => {
    const { rows, errors } = parseMetricsCsv('12,xiaohongshu,18400')

    expect(rows).toEqual([])
    expect(errors[0]).toContain('content_id')
    expect(errors[0]).toContain('platform')
  })

  it.each([
    ['content_id,platform,views\nabc,blog,10', 'content_id'],
    ['content_id,platform,views\n0,blog,10', 'content_id'],
    ['content_id,platform,views\n5,,10', 'platform'],
    ['content_id,platform,views\n5,my blog,10', 'platform'],
    ['content_id,platform,views\n5,blog,-3', 'views'],
    ['content_id,platform,views\n5,blog,1.5k', 'views'],
    ['content_id,platform,views,likes\n5,blog,10,3000000000', 'likes']
  ])('reports %j against line 2, naming %s', (csv, column) => {
    const { rows, errors } = parseMetricsCsv(csv)

    expect(rows).toEqual([])
    expect(errors).toHaveLength(1)
    expect(errors[0]).toContain('第 2 行')
    expect(errors[0]).toContain(column)
  })

  it('reports a thousands separator rather than importing the wrong number', () => {
    // "18,400" splits into two cells; taking the first would record 18 views.
    const { errors } = parseMetricsCsv('content_id,platform,views,likes\n5,blog,"18,400",7')

    expect(errors).toHaveLength(1)
    expect(errors[0]).toContain('第 2 行')
  })

  it('keeps the good rows and reports each bad line by its own number', () => {
    const { rows, errors } = parseMetricsCsv('content_id,platform,views\n1,blog,10\nx,blog,10\n3,blog,30\n4,blog,oops')

    expect(rows.map(row => row.content_id)).toEqual([1, 3])
    expect(errors.map(message => message.split('：')[0])).toEqual(['第 3 行', '第 5 行'])
  })

  it('refuses more rows than the API accepts in one request', () => {
    const lines = Array.from({ length: METRICS_IMPORT_MAX_ROWS + 1 }, (_, index) => `${index + 1},blog,1`)

    const { errors } = parseMetricsCsv(['content_id,platform,views', ...lines].join('\n'))

    expect(errors.join()).toContain(String(METRICS_IMPORT_MAX_ROWS))
  })

  it('says so when there is nothing to import', () => {
    expect(parseMetricsCsv('  \n ').errors).toHaveLength(1)
    expect(parseMetricsCsv('content_id,platform,views\n').errors).toHaveLength(1)
  })
})
