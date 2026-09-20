// Turns a pasted or uploaded spreadsheet export into import rows. Parsing happens
// in the browser so a bad line is reported with its line number before anything
// is sent; the API only ever receives rows that already satisfy its schema.
import type { MetricsImportRow } from '../api/metrics'

export const METRICS_IMPORT_MAX_ROWS = 500
export const METRICS_CSV_TEMPLATE = 'content_id,platform,views,likes,comments,shares\n12,xiaohongshu,18400,1240,96,210\n'

const REQUIRED_COLUMNS = ['content_id', 'platform', 'views'] as const
const COUNT_COLUMNS = ['views', 'likes', 'comments', 'shares'] as const
const METRIC_MAX = 2_000_000_000

export interface MetricsCsvResult {
  rows: MetricsImportRow[]
  errors: string[]
}

function splitLine(line: string, delimiter: string) {
  return line.split(delimiter).map(cell => cell.trim().replace(/^"(.*)"$/, '$1').trim())
}

function parseCount(raw: string | undefined) {
  if (raw === undefined || raw === '') return 0
  // Spreadsheets export 18,400 as "18400" but people paste "18 400" or "1.2e4".
  if (!/^\d+$/.test(raw)) return Number.NaN
  return Number(raw)
}

export function parseMetricsCsv(text: string): MetricsCsvResult {
  const lines = text
    .replace(/^﻿/, '')
    .split(/\r?\n/)
    .map((content, index) => ({ content: content.trim(), number: index + 1 }))
    .filter(line => line.content)

  if (!lines.length) return { rows: [], errors: ['没有可导入的数据。'] }

  // Excel pastes tab-separated cells; exported files use commas.
  const delimiter = lines[0].content.includes('\t') ? '\t' : ','
  const header = splitLine(lines[0].content, delimiter).map(name => name.toLowerCase())
  const missing = REQUIRED_COLUMNS.filter(name => !header.includes(name))
  if (missing.length) {
    return { rows: [], errors: [`首行必须是表头，缺少列：${missing.join('、')}。`] }
  }

  const rows: MetricsImportRow[] = []
  const errors: string[] = []
  for (const line of lines.slice(1)) {
    const cells = splitLine(line.content, delimiter)
    const cell = (name: string) => cells[header.indexOf(name)]

    const contentId = Number(cell('content_id'))
    if (!Number.isInteger(contentId) || contentId <= 0) {
      errors.push(`第 ${line.number} 行：content_id 必须是正整数。`)
      continue
    }
    const platform = (cell('platform') ?? '').toLowerCase()
    if (!/^[\p{L}\p{N}_-]{1,50}$/u.test(platform)) {
      errors.push(`第 ${line.number} 行：platform 只能包含字母、数字、下划线或连字符。`)
      continue
    }
    const counts = COUNT_COLUMNS.map(name => parseCount(header.includes(name) ? cell(name) : undefined))
    const badColumn = COUNT_COLUMNS.find((_, index) => !(counts[index] >= 0 && counts[index] <= METRIC_MAX))
    if (badColumn) {
      errors.push(`第 ${line.number} 行：${badColumn} 必须是不带分隔符的非负整数。`)
      continue
    }
    const [views, likes, comments, shares] = counts
    rows.push({ content_id: contentId, platform, views, likes, comments, shares })
  }

  if (rows.length > METRICS_IMPORT_MAX_ROWS) {
    errors.push(`一次最多导入 ${METRICS_IMPORT_MAX_ROWS} 行，当前 ${rows.length} 行，请拆分后再导入。`)
  }
  if (!rows.length && !errors.length) errors.push('表头之下没有数据行。')
  return { rows, errors }
}
