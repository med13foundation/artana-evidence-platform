import type { MonitorRow } from './source-workflow-monitor-utils'

export function filterWarningRows(eventRows: MonitorRow[]): MonitorRow[] {
  return eventRows.filter((row) => {
    const level = String(row.level ?? '').toLowerCase()
    const status = String(row.status ?? '').toLowerCase()
    return level === 'warning' || level === 'error' || status === 'failed'
  })
}
