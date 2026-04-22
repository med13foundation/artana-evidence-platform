export type MonitorRow = Record<string, unknown>

export function asRecord(value: unknown): MonitorRow {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? (value as MonitorRow)
    : {}
}

export function asList(value: unknown): MonitorRow[] {
  if (!Array.isArray(value)) {
    return []
  }
  return value
    .map((item) => asRecord(item))
    .filter((item) => Object.keys(item).length > 0)
}

export function displayValue(value: unknown): string {
  if (value === null || value === undefined) {
    return '—'
  }
  if (typeof value === 'string') {
    return value
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  return JSON.stringify(value)
}
